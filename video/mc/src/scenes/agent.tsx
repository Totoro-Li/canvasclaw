import {makeScene2D, Rect, Txt, Line, Layout, Circle} from '@motion-canvas/2d';
import {createRef, all, waitFor, chain, sequence, easeOutCubic, easeInOutCubic} from '@motion-canvas/core';

const FONT = 'Noto Sans CJK SC, WenQuanYi Zen Hei, sans-serif';
const BG = '#0d1117', BLUE = '#58a6ff', GREEN = '#3fb950', PURPLE = '#bc8cff', AMBER = '#d29922', INK = '#e6edf3';

function pill(txt: string, fill: string, w = 320, h = 86, fs = 30) {
  const ref = createRef<Rect>();
  const node = (
    <Rect ref={ref} width={w} height={h} radius={16} fill={'#161b22'} stroke={fill} lineWidth={3}
          opacity={0} scale={0.85} shadowColor={'#0008'} shadowBlur={18}>
      <Txt text={txt} fill={INK} fontFamily={FONT} fontSize={fs} fontWeight={600} textWrap maxWidth={w - 28} textAlign={'center'}/>
    </Rect>
  );
  return {ref, node};
}

export default makeScene2D(function* (view) {
  view.fill(BG);

  // ---------- Title ----------
  const title = createRef<Txt>();
  const sub = createRef<Txt>();
  view.add(<Txt ref={title} text={'CanvasClaw'} fill={INK} fontFamily={FONT} fontSize={120} fontWeight={800} opacity={0} y={-40}/>);
  view.add(<Txt ref={sub} text={'多智能体课程问答 · Orchestrator–Worker (LangGraph)'} fill={BLUE} fontFamily={FONT} fontSize={40} opacity={0} y={70}/>);
  yield* sequence(0.3, title().opacity(1, 0.7).to(1, 0.6), sub().opacity(1, 0.7));
  yield* waitFor(1.2);
  yield* all(title().opacity(0, 0.5), title().y(-360, 0.6, easeInOutCubic), sub().opacity(0, 0.5));

  // ---------- Persistent small title ----------
  const top = createRef<Txt>();
  view.add(<Txt ref={top} text={'CanvasClaw 智能体流水线'} fill={'#8b949e'} fontFamily={FONT} fontSize={30} y={-460} opacity={0}/>);
  yield* top().opacity(1, 0.4);

  // ---------- 1. Query ----------
  const q = pill('学生提问：\n“这门课怎么评分？”', BLUE, 380, 120, 32);
  q.ref().position([-720, -300]);
  view.add(q.node);
  yield* all(q.ref().opacity(1, 0.5), q.ref().scale(1, 0.5, easeOutCubic));
  yield* waitFor(0.4);

  // ---------- 2. Orchestrator ----------
  const orch = pill('Orchestrator\n调度器', PURPLE, 300, 110, 34);
  orch.ref().position([-180, -300]);
  view.add(orch.node);
  const a1 = createRef<Line>();
  view.add(<Line ref={a1} stroke={PURPLE} lineWidth={5} endArrow arrowSize={16} opacity={0}
                 points={[[-525, -300], [-335, -300]]}/>);
  yield* all(orch.ref().opacity(1, 0.5), orch.ref().scale(1, 0.5), a1().opacity(1, 0.4), a1().end(0).end(1, 0.5));
  yield* waitFor(0.3);

  // ---------- 3. Retrieve: 26 lecture chips ----------
  const grid = createRef<Layout>();
  view.add(<Layout ref={grid} layout gap={10} wrap={'wrap'} width={760} y={-110} x={300} alignItems={'center'} justifyContent={'center'}/>);
  const chips: Rect[] = [];
  for (let i = 1; i <= 26; i++) {
    const r = createRef<Rect>();
    grid().add(
      <Rect ref={r} width={84} height={46} radius={8} fill={'#161b22'} stroke={'#30363d'} lineWidth={2} opacity={0}>
        <Txt text={`L${String(i).padStart(2, '0')}`} fill={'#8b949e'} fontFamily={FONT} fontSize={22}/>
      </Rect>,
    );
    chips.push(r());
  }
  const lbl = createRef<Txt>();
  view.add(<Txt ref={lbl} text={'① 混合检索（向量 bge + BM25）over 全学期 26 讲'} fill={'#8b949e'} fontFamily={FONT} fontSize={26} y={-200} x={300} opacity={0}/>);
  yield* all(lbl().opacity(1, 0.4), sequence(0.02, ...chips.map(c => c.opacity(1, 0.3))));
  yield* waitFor(0.3);

  // ---------- 4. Route: highlight L01 + L21 ----------
  yield* lbl().text('② 路由：按匹配到的真实内容选中相关讲次', 0.4);
  const sel = [chips[0], chips[20]]; // L01, L21
  yield* all(...sel.map(c => all(c.stroke(GREEN, 0.4), c.lineWidth(4, 0.4), c.scale(1.18, 0.4),
             (c.children()[0] as Txt).fill(GREEN, 0.4))));
  yield* waitFor(0.5);

  // ---------- 5. Fan-out to workers ----------
  yield* lbl().text('③ 扇出：每个讲次一个 Worker 智能体并行作答', 0.4);
  const w1 = pill('Worker · L01-U02\nRAG 检索本单元', GREEN, 360, 110, 28);
  const w2 = pill('Worker · L21-U04\nRAG 检索本单元', GREEN, 360, 110, 28);
  w1.ref().position([300, 120]);
  w2.ref().position([300, 270]);
  view.add(w1.node); view.add(w2.node);
  const f1 = createRef<Line>(), f2 = createRef<Line>();
  view.add(<Line ref={f1} stroke={GREEN} lineWidth={4} endArrow arrowSize={14} opacity={0} points={[[-180, -245], [120, 120]]}/>);
  view.add(<Line ref={f2} stroke={GREEN} lineWidth={4} endArrow arrowSize={14} opacity={0} points={[[-180, -245], [120, 270]]}/>);
  yield* all(f1().opacity(1, 0.4), f2().opacity(1, 0.4),
             w1.ref().opacity(1, 0.5), w1.ref().scale(1, 0.5),
             w2.ref().opacity(1, 0.5), w2.ref().scale(1, 0.5));
  yield* waitFor(0.5);

  // ---------- 6. Aggregate ----------
  yield* lbl().text('④ 聚合：合并各 Worker，去重、按出处给出统一答案', 0.4);
  const agg = pill('Aggregate 聚合', AMBER, 300, 90, 32);
  agg.ref().position([760, 195]);
  view.add(agg.node);
  const g1 = createRef<Line>(), g2 = createRef<Line>();
  view.add(<Line ref={g1} stroke={AMBER} lineWidth={4} endArrow arrowSize={14} opacity={0} points={[[480, 120], [610, 195]]}/>);
  view.add(<Line ref={g2} stroke={AMBER} lineWidth={4} endArrow arrowSize={14} opacity={0} points={[[480, 270], [610, 195]]}/>);
  yield* all(g1().opacity(1, 0.4), g2().opacity(1, 0.4), agg.ref().opacity(1, 0.5), agg.ref().scale(1, 0.5));
  yield* waitFor(0.4);

  // ---------- 7. Answer + citation (spotlight: dim the pipeline) ----------
  yield* all(
    grid().opacity(0.14, 0.5), w1.ref().opacity(0.14, 0.5), w2.ref().opacity(0.14, 0.5),
    agg.ref().opacity(0.14, 0.5), q.ref().opacity(0.14, 0.5), orch.ref().opacity(0.14, 0.5),
    lbl().opacity(0, 0.4), a1().opacity(0.1, 0.4),
    f1().opacity(0.1, 0.5), f2().opacity(0.1, 0.5), g1().opacity(0.1, 0.5), g2().opacity(0.1, 0.5),
  );
  const ans = createRef<Rect>();
  view.add(
    <Rect ref={ans} width={1240} height={250} radius={20} fill={'#161b22'} stroke={BLUE} lineWidth={4}
          y={120} opacity={0} scale={0.9} shadowColor={'#000a'} shadowBlur={36}>
      <Layout layout direction={'column'} gap={18} padding={32} width={1240} alignItems={'start'}>
        <Txt text={'答：本课无传统考试，按 3 次课程作业 + 课程项目计分，共 100 分（作业 20 / 10 / 20 + 项目 50）。'}
             fill={INK} fontFamily={FONT} fontSize={34} fontWeight={600} textWrap maxWidth={1176}/>
        <Rect radius={12} fill={'#1f6feb33'} stroke={BLUE} lineWidth={2} padding={[10, 18]}>
          <Txt text={'📌 出处  [L01 · 课程考核  00:16:36 · slide 45]  —— 引用逐字核实 ✓'} fill={BLUE} fontFamily={FONT} fontSize={28}/>
        </Rect>
      </Layout>
    </Rect>,
  );
  yield* all(ans().opacity(1, 0.6), ans().scale(1, 0.6, easeOutCubic), ans().y(60, 0.6, easeOutCubic));
  yield* waitFor(2.2);
});
