<script setup>
// Password reset needs a backend endpoint that arrives with the
// notifications work package; until then the page is an honest placeholder.
import { useLocale } from '../../composables/useLocale'

const { t } = useLocale()

useHead({ title: 'Forgot password' })
</script>

<template>
  <section class="forgot" aria-labelledby="forgot-title">
    <div class="forgot__column">
      <h1 id="forgot-title" class="forgot__title">{{ t('auth.passwordReset') }}</h1>
      <p class="forgot__body">
        Password reset by email is not available in this demo build yet. If you cannot sign in,
        contact customer support for assistance.
      </p>
      <NuxtLink class="forgot__back" to="/auth/login">{{ t('auth.backToSignIn') }}</NuxtLink>
    </div>
  </section>
</template>

<style scoped>
/* 批次 B：与登录/注册页同一实测皮肤（380px 中央竖列，色值见 measurement.md）。 */
.forgot {
  display: flex;
  justify-content: center;
  padding: 40px 16px 96px;
  background: #fff;
}

.forgot__column {
  width: 380px;
  max-width: 100%;
}

.forgot__title {
  margin: 0 0 4px;
  color: #1a1a1a;
  font-size: 18px;
  font-weight: 700;
  line-height: 24px;
  text-align: center;
}

.forgot__body {
  margin: 24px 0 0;
  color: #6e7078;
  font-size: 14px;
  line-height: 20px;
}

.forgot__back {
  display: inline-block;
  margin-top: 16px;
  color: #1a1a1a;
  font-size: 14px;
  font-weight: 500;
  text-decoration: underline;
}

.forgot__back:hover {
  color: #e1251b;
}
</style>
