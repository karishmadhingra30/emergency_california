/** Insert each built client asset into the production service-worker precache. */
import { readdir, readFile, writeFile } from "node:fs/promises";
import { join, relative } from "node:path";

const client = new URL("../dist/client/", import.meta.url);
const root = new URL("../", import.meta.url);

async function files(directory) {
  const entries = await readdir(directory, { withFileTypes: true });
  const nested = await Promise.all(entries.map(async (entry) => entry.isDirectory() ? files(join(directory, entry.name)) : [join(directory, entry.name)]));
  return nested.flat();
}

const workerPath = new URL("sw.js", client);
const shell = (await files(client.pathname))
  .filter((file) => file !== workerPath.pathname)
  .map((file) => `/${relative(client.pathname, file)}`)
  .filter((asset) => !asset.startsWith("/.") && asset !== "/_headers");
const source = await readFile(new URL("public/sw.js", root), "utf8");
await writeFile(workerPath, source.replace("const APP_SHELL = [];", `const APP_SHELL = ${JSON.stringify(shell)};`));
console.log(`Service worker precaches ${shell.length} app-shell assets.`);
