"""Locked data contract for CanvasClaw. All modules import shapes from here.

Pipeline of artifacts:
  course.mp4
   ├─ data/transcript.json     (ASR: Segment[])
   ├─ data/slides/slides.json  (perceptual-hash keyframes: Slide[])
   ├─ data/slides/slides_ocr.json (vision-LLM OCR/desc per slide)
   └─ data/lecture_units.json  (segmentation: {units: LectureUnit[], chunks: Chunk[]})
        -> data/index/         (embeddings + BM25 over Chunk[])
"""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional, TypedDict, Annotated
import operator


# ---------- raw artifacts (TypedDict = JSON shapes on disk) ----------
class Segment(TypedDict):
    id: int
    start: float
    end: float
    ts: str                 # "HH:MM:SS"
    text: str
    is_question_candidate: bool
    words: List[Dict[str, Any]]


class Slide(TypedDict, total=False):
    slide_index: int
    start_sec: float
    end_sec: float
    ts: str
    frame: str              # path to jpg
    title: str              # filled by OCR step
    ocr_text: str           # filled by OCR step (vision LLM)


# ---------- derived structures ----------
@dataclass
class Chunk:
    chunk_id: str
    unit_id: str
    text: str
    start_sec: float
    end_sec: float
    ts: str
    lecture_id: str = "L01"             # which lecture/video this chunk belongs to
    slide_indices: List[int] = field(default_factory=list)
    source: str = "transcript"          # transcript | slide
    is_question: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class LectureUnit:
    unit_id: str                         # globally unique, e.g. "L03-U02"
    title: str
    slide_indices: List[int]
    start_sec: float
    end_sec: float
    ts: str
    lecture_id: str = "L01"              # parent lecture/video
    lecture_title: str = ""
    chunk_ids: List[str] = field(default_factory=list)
    summary: str = ""                    # short heuristic summary for routing
    transcript_text: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Citation:
    unit_id: str
    unit_title: str
    ts: str
    start_sec: float
    end_sec: float
    lecture_id: str = "L01"             # which video this citation points into
    lecture_title: str = ""
    slide_index: Optional[int] = None
    quote: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class WorkerOutput:
    unit_id: str
    unit_title: str
    answer: str
    found: bool
    citations: List[Citation] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        return d


@dataclass
class AnswerResult:
    query: str
    answer: str
    citations: List[Citation] = field(default_factory=list)
    units_used: List[str] = field(default_factory=list)
    meta: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        return d


# ---------- LangGraph state ----------
# worker_outputs uses an additive reducer so fan-out workers append concurrently.
class GraphState(TypedDict, total=False):
    query: str
    history: List[Dict[str, str]]            # [{role, content}, ...]
    scope: List[str]                         # restrict to these lecture_ids (None/[] = all)
    candidates: List[str]                    # unit_ids from retrieve_candidates
    selected_units: List[str]                # unit_ids chosen by select_lectures
    worker_outputs: Annotated[List[Dict[str, Any]], operator.add]
    answer: str
    citations: List[Dict[str, Any]]
    meta: Dict[str, Any]
