// Minimal dependency-free build. Real applications can use Tailwind/esbuild.
import { mkdir, copyFile } from 'node:fs/promises';
await mkdir('static', { recursive: true });
for (const extension of ['js', 'css']) {
  await copyFile(`frontend/index.${extension}`, `static/index.${extension}`);
}
