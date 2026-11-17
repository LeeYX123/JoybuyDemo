"""后台图片上传：校验 → 落盘（内容寻址）→ 返回可直接入库的 URL。

落盘路径由 ``media.storage.store_bytes`` 决定：
``<MEDIA_ROOT>/<kind>/original/<aa>/<bb>/<sha256>.<ext>``，
数据库只存相对路径，对外 URL 由 ``media_url()`` 拼成 ``/media/...``，
生产由 Nginx 直接服务该前缀，开发由 ``serve_media_file`` 兜底。

上传只接受 JPG / PNG / WebP（与需求文档一致），并按用途限制大小与像素，
**不信任客户端的 Content-Type 与文件名**：真实格式一律由 Pillow 解码判定。
"""

from io import BytesIO

from media.domain import MediaContentInvalid
from media.models import MediaAsset
from media.storage import media_url, store_bytes

# 文档里的上限：评价图 1MB，活动图/头像 2MB；商品图按运营要求放宽到 10MB
# （原图常常是 1248px 的高清实拍，1MB 太紧）。
PRODUCT_MAX_BYTES = 10 * 1024 * 1024
REVIEW_MAX_BYTES = 1 * 1024 * 1024
CMS_MAX_BYTES = 2 * 1024 * 1024
MERCHANT_MAX_BYTES = 2 * 1024 * 1024

# 解压炸弹防护：限制解码后的总像素数（8000×6000 之类的大图直接拒绝）。
MAX_PIXELS = 40_000_000

# Pillow 的 format 名 → 对外 MIME。只放白名单，其余一律拒绝。
ALLOWED_FORMATS = {
    "JPEG": "image/jpeg",
    "PNG": "image/png",
    "WEBP": "image/webp",
}

# 用途 → (MediaAsset.Kind, 大小上限)。前端只传 purpose，不直接传 kind。
PURPOSES = {
    "product": (MediaAsset.Kind.PRODUCT, PRODUCT_MAX_BYTES),
    "review": (MediaAsset.Kind.REVIEW, REVIEW_MAX_BYTES),
    "banner": (MediaAsset.Kind.CMS, CMS_MAX_BYTES),
    "channel_banner": (MediaAsset.Kind.CMS, CMS_MAX_BYTES),
    "activity": (MediaAsset.Kind.CMS, CMS_MAX_BYTES),
    "avatar": (MediaAsset.Kind.MERCHANT, MERCHANT_MAX_BYTES),
    # 2026-11-17 开店申请：店铺 logo 与个人证件照（买家侧上传，2MB，
    # 落 MERCHANT 桶；证件照属敏感信息，仅本人提交 / 平台审核读取）。
    "shop_application": (MediaAsset.Kind.MERCHANT, MERCHANT_MAX_BYTES),
}


class UploadError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400):
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def read_limited(file, *, max_bytes: int) -> bytes:
    """读取上传内容，超过上限立即中断，避免把超大文件读进内存。"""

    declared = getattr(file, "size", None)
    if declared is not None and declared > max_bytes:
        raise UploadError(
            "FILE_TOO_LARGE",
            f"图片不能超过 {max_bytes // (1024 * 1024)}MB。",
            status_code=413,
        )

    chunks = []
    total = 0
    while True:
        chunk = file.read(256 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise UploadError(
                "FILE_TOO_LARGE",
                f"图片不能超过 {max_bytes // (1024 * 1024)}MB。",
                status_code=413,
            )
        chunks.append(chunk)

    if total == 0:
        raise UploadError("FILE_EMPTY", "上传的文件是空的。")
    return b"".join(chunks)


def inspect_image(data: bytes) -> tuple[str, int, int]:
    """解出真实格式与尺寸。格式不在白名单、像素超限或解不开都拒绝。"""

    try:
        from PIL import Image
    except ImportError as exc:  # pragma: no cover - 依赖已在 requirements 里
        raise UploadError("IMAGE_SUPPORT_MISSING", "服务器缺少图片处理组件。", 500) from exc

    # 先用 verify() 确认不是伪装成图片的可执行内容，再重新打开拿尺寸
    # （verify() 之后对象不可再用，这是 Pillow 的既有约定）。
    try:
        with Image.open(BytesIO(data)) as probe:
            fmt = (probe.format or "").upper()
            probe.verify()
    except Exception as exc:
        raise UploadError("FILE_NOT_IMAGE", "文件不是有效的图片。") from exc

    if fmt not in ALLOWED_FORMATS:
        raise UploadError(
            "IMAGE_FORMAT_UNSUPPORTED",
            "只支持 JPG、PNG、WebP 格式的图片。",
        )

    try:
        with Image.open(BytesIO(data)) as image:
            width, height = image.size
    except Exception as exc:
        raise UploadError("FILE_NOT_IMAGE", "文件不是有效的图片。") from exc

    if width <= 0 or height <= 0:
        raise UploadError("IMAGE_DIMENSION_INVALID", "图片尺寸不正确。")
    if width * height > MAX_PIXELS:
        raise UploadError(
            "IMAGE_TOO_LARGE_PIXELS",
            f"图片像素过大（{width}×{height}），请压缩后再上传。",
        )
    return ALLOWED_FORMATS[fmt], width, height


def store_upload(file, *, purpose: str, source_url: str = "") -> dict:
    """校验并落盘，返回前端可直接使用的 URL 与元数据。"""

    resolved = PURPOSES.get(str(purpose or "").strip().lower())
    if resolved is None:
        raise UploadError(
            "UPLOAD_PURPOSE_INVALID",
            f"上传用途不正确，可选：{'、'.join(sorted(PURPOSES))}。",
        )
    kind, max_bytes = resolved

    data = read_limited(file, max_bytes=max_bytes)
    mime_type, width, height = inspect_image(data)

    try:
        asset, created = store_bytes(
            data,
            kind=kind,
            mime_type=mime_type,
            source_url=source_url,
        )
    except MediaContentInvalid as exc:
        raise UploadError("FILE_NOT_IMAGE", "文件不是有效的图片。") from exc

    return {
        "url": media_url(asset.relative_path),
        "sha256": asset.sha256,
        "mime_type": asset.mime_type,
        "width": asset.width or width,
        "height": asset.height or height,
        "byte_size": asset.byte_size,
        "deduplicated": not created,
    }
