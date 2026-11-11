import path from "node:path";
import type { NextConfig } from "next";
const config: NextConfig = { output: "standalone", outputFileTracingRoot: path.join(process.cwd()) };
export default config;
