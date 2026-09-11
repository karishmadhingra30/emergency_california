/** Build the canonical bundle and copy its exact files into PWA static assets. */
import { execFileSync } from "node:child_process";
import { copyFile, mkdir } from "node:fs/promises";
import { fileURLToPath } from "node:url";

const repo = new URL("../../", import.meta.url);
const source = new URL("bundle/", repo);
const destination = new URL("../public/bundle/", import.meta.url);

execFileSync("python", ["backend/build_bundle.py"], { cwd: fileURLToPath(repo), stdio: "inherit" });
await mkdir(destination, { recursive: true });
await Promise.all(["bundle.db", "manifest.json"].map((name) => copyFile(new URL(name, source), new URL(name, destination))));
