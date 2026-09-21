import tseslint from "@typescript-eslint/eslint-plugin";
import tsparser from "@typescript-eslint/parser";
import pluginVue from "eslint-plugin-vue";
import vueParser from "vue-eslint-parser";

export default [
  ...pluginVue.configs["flat/recommended"],
  {
    files: ["**/*.{ts,vue}"],
    languageOptions: { parser: vueParser, parserOptions: { parser: tsparser, extraFileExtensions: [".vue"] } },
    plugins: { "@typescript-eslint": tseslint },
    rules: { "vue/multi-word-component-names": "off" },
  },
  { ignores: ["dist/", "node_modules/"] },
];
