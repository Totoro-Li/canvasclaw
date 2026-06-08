export const meta = {
  name: 'canvasclaw-judge',
  description: 'LLM-judge each CanvasClaw eval answer for routing/faithfulness/quality; adversarial second pass on disputed ones',
  phases: [
    { title: 'Judge', detail: 'one judge per question (routing + faithfulness + quality)' },
    { title: 'Adversarial', detail: 'skeptic re-checks questions the first judge marked correct' },
  ],
}

// args = array of eval records: {id, kind, query, answer, expected_lecture, lectures_cited, citations:[{lecture_id,ts,quote,_grounding}], n_citations, n_grounded}
const results = Array.isArray(args) ? args : (args && args.records) || []

const VERDICT = {
  type: 'object', additionalProperties: false,
  properties: {
    routing_ok: { type: 'boolean', description: '引用讲次主题是否与问题相关（oos类问题：是否正确判断为未覆盖）' },
    faithful: { type: 'integer', description: '1-5，回答是否被引用片段支持、无编造' },
    answer_quality: { type: 'integer', description: '1-5，回答是否准确、具体、有用' },
    correct: { type: 'boolean', description: '综合：是否为一个好且有据的回答' },
    issue: { type: 'string', description: '一句话问题说明或 none' },
  },
  required: ['routing_ok', 'faithful', 'answer_quality', 'correct', 'issue'],
}

const fmtCites = (r) => (r.citations || []).map(c =>
  `  [${c.lecture_id} ${c.ts}] grounded=${c.grounded} 原文“${(c.quote||'').slice(0,50)}”`).join('\n') || '  (无引用)'

const judgePrompt = (r) => `你是课程问答智能体 CanvasClaw 的严格评测员。这是一门《智能体及应用》研究生课程（26讲，其中7讲源音频损坏无转写）。
问题类别: ${r.kind}
问题: ${r.query}
智能体回答: ${(r.answer||'').slice(0,1200)}
引用来源(讲次/时间/该原文是否已在ASR转写中逐字核实):
${fmtCites(r)}
${r.expected_lecture ? '出题所基于的讲次: ' + r.expected_lecture : ''}

请判断：
1 routing_ok：引用/作答所指讲次主题是否与问题相关；对“这门课讲过X吗”类(oos)问题，若课程确无该主题且回答如实说明“未涉及”，则 routing_ok=true。
2 faithful(1-5)：回答是否被引用片段支持、无明显编造（grounded=false 的引用要扣分）。
3 answer_quality(1-5)：回答是否准确、具体、有用。
4 correct：综合是否为“好且有据”的回答。
5 issue：一句话指出主要问题，或填 none。
只返回 JSON。`

const adversarialPrompt = (r, v) => `复核：下面这条课程问答被初评为“正确”。请以怀疑态度找出它是否其实存在问题（路由错讲、引用与回答不符、编造、答非所问）。默认严格。
问题: ${r.query}
回答: ${(r.answer||'').slice(0,1000)}
引用:
${fmtCites(r)}
初评: ${JSON.stringify(v)}
只返回 JSON：是否仍然 correct，以及 issue。`

const judged = await pipeline(
  results,
  (r) => agent(judgePrompt(r), { schema: VERDICT, phase: 'Judge', label: 'judge:' + (r.model||'') + ':' + r.id })
            .then(v => ({ id: r.id, kind: r.kind, model: r.model || 'default', ...v })),
  (v, r) => (v && v.correct)
      ? agent(adversarialPrompt(r, v), { schema: VERDICT, phase: 'Adversarial', label: 'adv:' + (r.model||'') + ':' + r.id })
          .then(a => ({ ...v, correct: v.correct && a.correct, adv_issue: a.issue }))
      : v
)

const ok = judged.filter(Boolean)
const summarize = (arr) => ({
  n: arr.length,
  correct: arr.filter(v => v.correct).length,
  correct_pct: arr.length ? Math.round(arr.filter(v => v.correct).length / arr.length * 100) : 0,
  routing_ok: arr.filter(v => v.routing_ok).length,
  avg_faithful: +(arr.reduce((s, v) => s + (v.faithful || 0), 0) / (arr.length||1)).toFixed(2),
  avg_quality: +(arr.reduce((s, v) => s + (v.answer_quality || 0), 0) / (arr.length||1)).toFixed(2),
  by_kind: arr.reduce((m, v) => { (m[v.kind] = m[v.kind] || { n: 0, correct: 0 }); m[v.kind].n++; m[v.kind].correct += v.correct ? 1 : 0; return m }, {}),
})
const byModel = {}
for (const v of ok) (byModel[v.model] = byModel[v.model] || []).push(v)
const models = {}
for (const m in byModel) models[m] = summarize(byModel[m])
return { models, overall: summarize(ok), verdicts: ok }
