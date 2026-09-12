import { spawnSync } from 'node:child_process'
import { existsSync, unlinkSync, writeFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

const probePath = fileURLToPath(
  new globalThis.URL('../src/__typecheck_guard_mutation__.ts', import.meta.url)
)

if (existsSync(probePath)) {
  throw new Error(`Refusing to overwrite existing probe: ${probePath}`)
}

try {
  writeFileSync(probePath, 'const breakoutTypecheckProbe: string = 42\n')
  const result = spawnSync(
    globalThis.process.platform === 'win32' ? 'npm.cmd' : 'npm',
    ['run', 'typecheck'],
    { encoding: 'utf8' }
  )
  const output = `${result.stdout ?? ''}\n${result.stderr ?? ''}`

  if (result.status === 0 || !output.includes('TS2322')) {
    globalThis.process.stderr.write(output)
    throw new Error('The typecheck gate did not reject the expected TS2322 mutation')
  }

  globalThis.process.stdout.write('Typecheck guard rejected the expected mutation.\n')
} finally {
  if (existsSync(probePath)) unlinkSync(probePath)
}
