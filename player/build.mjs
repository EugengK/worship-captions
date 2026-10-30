// Bundles the worship player for the browser: our src/ plus IeumOffice's pptx engine,
// layout and slide drawing, taken from a checkout of the commit pinned in
// ../ieumoffice/UPSTREAM_COMMIT. Output goes to dist/ (committed, so the Mac needs no Node).
//
//   IEUM_DIR=/path/to/openoffice node build.mjs     # default: ./.ieum (see build.sh)
import { build } from 'esbuild'
import { readFileSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { createRequire } from 'node:module'
import { execFileSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'

const here = dirname(fileURLToPath(import.meta.url))
const ieum = resolve(process.env.IEUM_DIR || join(here, '.ieum'))
const want = readFileSync(join(here, '../ieumoffice/UPSTREAM_COMMIT'), 'utf8').trim()
const head = execFileSync('git', ['-C', ieum, 'rev-parse', 'HEAD'], { encoding: 'utf8' }).trim()
if (head !== want) console.warn(`warning: IeumOffice checkout is at ${head}, pinned commit is ${want}`)

const slidesReq = createRequire(join(ieum, 'apps/slides/package.json'))
const pkg = (name) => dirname(slidesReq.resolve(`${name}/package.json`))
const shim = (f) => join(here, 'src/shims', f)

await build({
  entryPoints: { presenter: join(here, 'src/presenter.tsx'), audience: join(here, 'src/audience.tsx') },
  outdir: join(here, 'dist'),
  bundle: true,
  format: 'iife',
  platform: 'browser',
  target: ['chrome110', 'safari16'],
  minify: true,
  sourcemap: false,
  legalComments: 'eof',
  tsconfig: join(ieum, 'apps/slides/tsconfig.json'),
  jsx: 'automatic',
  define: { 'process.env.NODE_ENV': '"production"', global: 'globalThis' },
  inject: [shim('buffer-global.ts')],
  alias: {
    'node:crypto': shim('node-crypto.ts'),
    'node:zlib': shim('node-unsupported.ts'),
    'node:fs': shim('node-unsupported.ts'),
    'node:stream/promises': shim('node-unsupported.ts'),
    'ieum-slides': join(ieum, 'apps/slides/src/renderer'),
    react: pkg('react'),
    'react-dom': pkg('react-dom'),
    konva: pkg('konva'),
    'react-konva': pkg('react-konva'),
  },
  nodePaths: [join(here, 'node_modules'), join(ieum, 'apps/slides/node_modules'), join(ieum, 'node_modules')],
  logLevel: 'warning',
})
console.log('built dist/presenter.js, dist/audience.js')
