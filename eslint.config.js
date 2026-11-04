import js from '@eslint/js'
import pluginVue from 'eslint-plugin-vue'
import globals from 'globals'

export default [
  {
    ignores: ['**/node_modules/**', '**/.nuxt/**', '**/.output/**', '**/dist/**', 'var/**'],
  },
  js.configs.recommended,
  ...pluginVue.configs['flat/recommended'],
  {
    files: ['**/*.{js,vue}'],
    languageOptions: {
      ecmaVersion: 'latest',
      sourceType: 'module',
      globals: {
        ...globals.browser,
        ...globals.node,
      },
    },
    rules: {
      // Formatting belongs to Prettier; these stylistic rules fight it.
      'vue/html-indent': 'off',
      'vue/html-self-closing': 'off',
      'vue/max-attributes-per-line': 'off',
      'vue/singleline-html-element-content-newline': 'off',
      'vue/multiline-html-element-content-newline': 'off',
      'vue/html-closing-bracket-newline': 'off',
      'vue/first-attribute-linebreak': 'off',
      'vue/attribute-hyphenation': 'off',
      'vue/multi-word-component-names': 'off',
    },
  },
  {
    files: ['storefront/**/*.{js,vue}'],
    languageOptions: {
      globals: {
        clearError: 'readonly',
        computed: 'readonly',
        defineNuxtConfig: 'readonly',
        $fetch: 'readonly',
        definePageMeta: 'readonly',
        defineProps: 'readonly',
        navigateTo: 'readonly',
        onMounted: 'readonly',
        ref: 'readonly',
        reloadNuxtApp: 'readonly',
        useAsyncData: 'readonly',
        useCookie: 'readonly',
        useFetch: 'readonly',
        useHead: 'readonly',
        useRequestHeaders: 'readonly',
        useRoute: 'readonly',
        useRouter: 'readonly',
        useRuntimeConfig: 'readonly',
        useSearch: 'readonly',
        useSeoMeta: 'readonly',
        useState: 'readonly',
      },
    },
  },
]
