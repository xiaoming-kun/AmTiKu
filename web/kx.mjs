import katex from 'katex'
import fs from 'node:fs'
const sol = fs.readFileSync('/tmp/ruku/sol.txt', 'utf8')
const segs = [...sol.matchAll(/\$([^$]*)\$/g)].map(m => m[1])
let bad = 0
segs.forEach((t, i) => {
  try { katex.renderToString(t, { throwOnError: true, displayMode: false }) }
  catch (e) { bad++; console.log('✗ #' + i + ' ' + JSON.stringify(t).slice(0, 200)); console.log('   ' + String(e.message).slice(0, 120)) }
})
console.log('共 ' + segs.length + ' 段行内公式，失败 ' + bad)
