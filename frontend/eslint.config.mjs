import js from "@eslint/js";
import tseslint from "typescript-eslint";

const config = tseslint.config(
  { ignores: [".next/**", "out/**", "build/**"] },
  js.configs.recommended,
  ...tseslint.configs.recommended,
);

export default config;
