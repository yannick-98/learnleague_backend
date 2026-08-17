"""
Motor de generación académica de preguntas — LearnLeague.

Pipeline de alto nivel:
  1. Perfil pedagógico   → audiencia, Bloom, complejidad lingüística
  2. Análisis de texto   → segmentación, puntuación semántica, conceptos
  3. Plan de evaluación  → distribución cognitiva + cobertura del temario
  4. Síntesis            → OpenAI (prompt enriquecido) o mock heurístico
  5. Control de calidad  → validación, deduplicación, equilibrio de ítems
"""
from __future__ import annotations

import json
import logging
import math
import random
import re
import textwrap
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from django.conf import settings

logger = logging.getLogger(__name__)

VALID_OPTIONS = {'A', 'B', 'C', 'D'}
DIFFICULTY_LEVELS = {'easy', 'medium', 'hard', 'mixed'}
DIFFICULTY_LABELS_ES = {
    'easy': 'fácil', 'medium': 'media', 'hard': 'difícil', 'mixed': 'mixta',
}

# ─── Taxonomía de Bloom (niveles cognitivos) ───────────────────────────────

class BloomLevel(str, Enum):
    REMEMBER = 'remember'
    UNDERSTAND = 'understand'
    APPLY = 'apply'
    ANALYZE = 'analyze'
    EVALUATE = 'evaluate'

    @property
    def label_es(self) -> str:
        return {
            BloomLevel.REMEMBER: 'Recuerdo',
            BloomLevel.UNDERSTAND: 'Comprensión',
            BloomLevel.APPLY: 'Aplicación',
            BloomLevel.ANALYZE: 'Análisis',
            BloomLevel.EVALUATE: 'Evaluación',
        }[self]


class QuestionArchetype(str, Enum):
    DEFINITION = 'definition'
    FACT_RECALL = 'fact_recall'
    INFERENCE = 'inference'
    CAUSE_EFFECT = 'cause_effect'
    COMPARISON = 'comparison'
    APPLICATION = 'application'
    BEST_STATEMENT = 'best_statement'
    ERROR_IDENTIFICATION = 'error_identification'


# ─── Perfiles por nivel educativo ────────────────────────────────────────────

@dataclass(frozen=True)
class EducationProfile:
    """Parámetros pedagógicos adaptados a la edad y etapa formativa."""
    level_key: str
    label: str
    age_range: str
    reading_grade: str
    max_question_words: int
    max_option_words: int
    bloom_weights: dict[BloomLevel, float]
    archetype_pool: tuple[QuestionArchetype, ...]
    tone_guidance: str
    vocabulary_guidance: str

    def bloom_distribution(self, n: int) -> list[BloomLevel]:
        """Asigna n niveles Bloom según pesos del perfil (método largest remainder)."""
        levels = list(self.bloom_weights.keys())
        weights = [self.bloom_weights[l] for l in levels]
        total = sum(weights) or 1.0
        raw = [w / total * n for w in weights]
        counts = [int(x) for x in raw]
        remainder = n - sum(counts)
        fractions = sorted(
            enumerate(raw),
            key=lambda x: x[1] - counts[x[0]],
            reverse=True,
        )
        for i in range(remainder):
            counts[fractions[i % len(fractions)][0]] += 1
        result: list[BloomLevel] = []
        for level, count in zip(levels, counts):
            result.extend([level] * count)
        random.shuffle(result)
        return result


EDUCATION_PROFILES: dict[str, EducationProfile] = {
    'primary': EducationProfile(
        level_key='primary',
        label='Educación Primaria',
        age_range='6–11 años',
        reading_grade='Lenguaje concreto, frases cortas',
        max_question_words=22,
        max_option_words=12,
        bloom_weights={
            BloomLevel.REMEMBER: 0.45,
            BloomLevel.UNDERSTAND: 0.40,
            BloomLevel.APPLY: 0.15,
            BloomLevel.ANALYZE: 0.0,
            BloomLevel.EVALUATE: 0.0,
        },
        archetype_pool=(
            QuestionArchetype.FACT_RECALL,
            QuestionArchetype.DEFINITION,
            QuestionArchetype.INFERENCE,
        ),
        tone_guidance='Cercano y motivador; evita tecnicismos innecesarios.',
        vocabulary_guidance='Usa vocabulario de uso cotidiano; define términos nuevos en la explicación.',
    ),
    'secondary': EducationProfile(
        level_key='secondary',
        label='Educación Secundaria (ESO)',
        age_range='12–15 años',
        reading_grade='Lenguaje académico introductorio',
        max_question_words=28,
        max_option_words=16,
        bloom_weights={
            BloomLevel.REMEMBER: 0.25,
            BloomLevel.UNDERSTAND: 0.35,
            BloomLevel.APPLY: 0.25,
            BloomLevel.ANALYZE: 0.10,
            BloomLevel.EVALUATE: 0.05,
        },
        archetype_pool=(
            QuestionArchetype.FACT_RECALL,
            QuestionArchetype.DEFINITION,
            QuestionArchetype.INFERENCE,
            QuestionArchetype.CAUSE_EFFECT,
            QuestionArchetype.APPLICATION,
        ),
        tone_guidance='Claro y riguroso; fomenta el razonamiento.',
        vocabulary_guidance='Terminología propia de la asignatura con contexto suficiente.',
    ),
    'bachillerato': EducationProfile(
        level_key='bachillerato',
        label='Bachillerato',
        age_range='16–18 años',
        reading_grade='Discurso académico intermedio-alto',
        max_question_words=35,
        max_option_words=20,
        bloom_weights={
            BloomLevel.REMEMBER: 0.15,
            BloomLevel.UNDERSTAND: 0.25,
            BloomLevel.APPLY: 0.25,
            BloomLevel.ANALYZE: 0.25,
            BloomLevel.EVALUATE: 0.10,
        },
        archetype_pool=tuple(QuestionArchetype),
        tone_guidance='Exigente; prioriza interpretación y transferencia.',
        vocabulary_guidance='Precisión terminológica; enunciados sin ambigüedad.',
    ),
    'fp': EducationProfile(
        level_key='fp',
        label='Formación Profesional',
        age_range='16+ años',
        reading_grade='Lenguaje aplicado y procedimental',
        max_question_words=32,
        max_option_words=18,
        bloom_weights={
            BloomLevel.REMEMBER: 0.20,
            BloomLevel.UNDERSTAND: 0.25,
            BloomLevel.APPLY: 0.35,
            BloomLevel.ANALYZE: 0.15,
            BloomLevel.EVALUATE: 0.05,
        },
        archetype_pool=(
            QuestionArchetype.APPLICATION,
            QuestionArchetype.CAUSE_EFFECT,
            QuestionArchetype.BEST_STATEMENT,
            QuestionArchetype.ERROR_IDENTIFICATION,
            QuestionArchetype.FACT_RECALL,
        ),
        tone_guidance='Orientado a procedimientos, casos reales y criterios profesionales.',
        vocabulary_guidance='Vocabulario técnico-profesional del sector.',
    ),
    'university': EducationProfile(
        level_key='university',
        label='Educación Universitaria',
        age_range='18+ años',
        reading_grade='Discurso científico y argumentativo',
        max_question_words=45,
        max_option_words=28,
        bloom_weights={
            BloomLevel.REMEMBER: 0.10,
            BloomLevel.UNDERSTAND: 0.20,
            BloomLevel.APPLY: 0.20,
            BloomLevel.ANALYZE: 0.30,
            BloomLevel.EVALUATE: 0.20,
        },
        archetype_pool=tuple(QuestionArchetype),
        tone_guidance='Nivel universitario; exige síntesis, contraste de modelos y evidencia.',
        vocabulary_guidance='Registro académico; referencias implícitas al marco teórico del texto.',
    ),
    'professional': EducationProfile(
        level_key='professional',
        label='Formación Profesional',
        age_range='Adultos',
        reading_grade='Lenguaje aplicado',
        max_question_words=32,
        max_option_words=18,
        bloom_weights={
            BloomLevel.REMEMBER: 0.20,
            BloomLevel.UNDERSTAND: 0.25,
            BloomLevel.APPLY: 0.35,
            BloomLevel.ANALYZE: 0.15,
            BloomLevel.EVALUATE: 0.05,
        },
        archetype_pool=(
            QuestionArchetype.APPLICATION,
            QuestionArchetype.CAUSE_EFFECT,
            QuestionArchetype.BEST_STATEMENT,
            QuestionArchetype.ERROR_IDENTIFICATION,
        ),
        tone_guidance='Enfoque competencial y aplicado.',
        vocabulary_guidance='Terminología profesional contextualizada.',
    ),
    'other': EducationProfile(
        level_key='other',
        label='Público general / mixto',
        age_range='Todas las edades',
        reading_grade='Adaptable',
        max_question_words=30,
        max_option_words=18,
        bloom_weights={
            BloomLevel.REMEMBER: 0.20,
            BloomLevel.UNDERSTAND: 0.30,
            BloomLevel.APPLY: 0.25,
            BloomLevel.ANALYZE: 0.15,
            BloomLevel.EVALUATE: 0.10,
        },
        archetype_pool=tuple(QuestionArchetype),
        tone_guidance='Equilibrado; accesible pero riguroso.',
        vocabulary_guidance='Claridad prioritaria; evita jerga no explicada.',
    ),
}

DEFAULT_PROFILE = EDUCATION_PROFILES['other']


def _resolve_profile(education_level: str | None) -> EducationProfile:
    if not education_level:
        return DEFAULT_PROFILE
    return EDUCATION_PROFILES.get(education_level.strip().lower(), DEFAULT_PROFILE)


# ─── Contexto y plan de generación ───────────────────────────────────────────

@dataclass
class GenerationContext:
    text: str
    num_questions: int
    difficulty: str = 'medium'
    education_level: str | None = None
    subject: str | None = None
    activity_title: str | None = None
    material_title: str | None = None

    def __post_init__(self) -> None:
        self.difficulty = self.difficulty if self.difficulty in DIFFICULTY_LEVELS else 'medium'
        self.num_questions = max(1, min(self.num_questions, 50))

    @property
    def profile(self) -> EducationProfile:
        return _resolve_profile(self.education_level)


@dataclass
class TextChunk:
    index: int
    text: str
    score: float
    concepts: list[str] = field(default_factory=list)
    sentences: list[str] = field(default_factory=list)


@dataclass
class QuestionSlot:
    order: int
    chunk: TextChunk
    bloom: BloomLevel
    difficulty: str
    archetype: QuestionArchetype


# ─── Análisis de texto ───────────────────────────────────────────────────────

_DEFINITION_RE = re.compile(
    r'\b(?:es|son|consiste en|se define como|significa|representa|denomina)\b',
    re.IGNORECASE,
)
_CAUSAL_RE = re.compile(
    r'\b(?:porque|por tanto|por consiguiente|debido a|causa|conduce a|provoca|origina)\b',
    re.IGNORECASE,
)
_COMPARISON_RE = re.compile(
    r'\b(?:sin embargo|mientras que|a diferencia|frente a|comparado|mayor|menor)\b',
    re.IGNORECASE,
)


class TextAnalyzer:
    """Segmenta y puntúa el material fuente para maximizar cobertura evaluativa."""

    MIN_CHUNK_CHARS = 80
    TARGET_CHUNK_CHARS = 420

    def analyze(self, text: str, max_chunks: int = 24) -> list[TextChunk]:
        paragraphs = self._segment(text)
        chunks: list[TextChunk] = []
        for idx, para in enumerate(paragraphs):
            score = self._score_paragraph(para)
            concepts = self._extract_concepts(para)
            sentences = self._split_sentences(para)
            chunks.append(TextChunk(
                index=idx, text=para, score=score,
                concepts=concepts, sentences=sentences,
            ))
        chunks.sort(key=lambda c: c.score, reverse=True)
        return chunks[:max_chunks]

    def _segment(self, text: str) -> list[str]:
        text = re.sub(r'\r\n?', '\n', text.strip())
        parts = [p.strip() for p in re.split(r'\n{2,}', text) if len(p.strip()) >= self.MIN_CHUNK_CHARS]
        if len(parts) >= 2:
            return parts
        parts = [p.strip() for p in text.split('\n') if len(p.strip()) >= self.MIN_CHUNK_CHARS]
        if parts:
            return parts
        return self._chunk_by_words(text)

    def _chunk_by_words(self, text: str) -> list[str]:
        words = text.split()
        chunks, buf, size = [], [], 0
        for word in words:
            buf.append(word)
            size += len(word) + 1
            if size >= self.TARGET_CHUNK_CHARS:
                chunks.append(' '.join(buf))
                buf, size = [], 0
        if buf:
            chunks.append(' '.join(buf))
        return [c for c in chunks if len(c) >= self.MIN_CHUNK_CHARS] or ([text] if text else [])

    def _score_paragraph(self, para: str) -> float:
        score = 0.0
        sentences = self._split_sentences(para)
        score += min(len(sentences), 6) * 1.5
        long_words = [w for w in re.findall(r'\b[A-Za-zÁ-ÿ]{5,}\b', para) if w.lower() not in _STOPWORDS_ES]
        score += min(len(set(w.lower() for w in long_words)), 12) * 0.8
        if _DEFINITION_RE.search(para):
            score += 4.0
        if _CAUSAL_RE.search(para):
            score += 3.0
        if _COMPARISON_RE.search(para):
            score += 2.5
        if re.search(r'\d+', para):
            score += 1.5
        if re.search(r'[:;—–-]', para):
            score += 0.5
        return score

    def _split_sentences(self, text: str) -> list[str]:
        return [
            s.strip() for s in re.split(r'(?<=[.!?…])\s+', text)
            if len(s.strip()) >= 25
        ]

    def _extract_concepts(self, text: str) -> list[str]:
        candidates: list[str] = []
        for match in re.finditer(
            r'\b([A-ZÁÉÍÓÚÑ][a-záéíóúñ]+(?:\s+(?:de|del|la|el|y|en))?\s*[A-ZÁÉÍÓÚÑ]?[a-záéíóúñ]{3,})\b',
            text,
        ):
            term = match.group(1).strip()
            if len(term) > 4 and term.lower() not in _STOPWORDS_ES:
                candidates.append(term)
        for word in re.findall(r'\b[A-ZÁÉÍÓÚÑ][a-záéíóúñ]{4,}\b', text):
            if word.lower() not in _STOPWORDS_ES:
                candidates.append(word)
        seen: set[str] = set()
        unique: list[str] = []
        for c in candidates:
            key = c.lower()
            if key not in seen:
                seen.add(key)
                unique.append(c)
        return unique[:8]


_STOPWORDS_ES = frozenset({
    'sobre', 'desde', 'hasta', 'donde', 'cuando', 'entre', 'todos', 'todas',
    'este', 'esta', 'estos', 'estas', 'como', 'para', 'porque', 'también',
    'puede', 'pueden', 'debe', 'deben', 'tiene', 'tienen', 'hace', 'hacia',
    'The', 'This', 'That', 'With', 'From', 'Which', 'When', 'Where',
})


class AssessmentPlanner:
    """Construye un plan de ítems: cobertura temática + distribución cognitiva."""

    def build_plan(self, ctx: GenerationContext, chunks: list[TextChunk]) -> list[QuestionSlot]:
        profile = ctx.profile
        bloom_levels = profile.bloom_distribution(ctx.num_questions)
        difficulties = self._difficulty_schedule(ctx.num_questions, ctx.difficulty)
        usable = chunks or [TextChunk(index=0, text=ctx.text[:2000], score=1.0)]

        slots: list[QuestionSlot] = []
        for i in range(ctx.num_questions):
            chunk = usable[i % len(usable)]
            bloom = bloom_levels[i] if i < len(bloom_levels) else BloomLevel.UNDERSTAND
            archetype = self._pick_archetype(profile, bloom, i)
            slots.append(QuestionSlot(
                order=i,
                chunk=chunk,
                bloom=bloom,
                difficulty=difficulties[i],
                archetype=archetype,
            ))
        return slots

    def _difficulty_schedule(self, n: int, difficulty: str) -> list[str]:
        if difficulty == 'mixed':
            easy = n // 3
            hard = n // 3
            medium = n - easy - hard
            pool = ['easy'] * easy + ['medium'] * medium + ['hard'] * hard
            random.shuffle(pool)
            return pool
        return [difficulty] * n

    def _pick_archetype(
        self, profile: EducationProfile, bloom: BloomLevel, seed: int,
    ) -> QuestionArchetype:
        bloom_map: dict[BloomLevel, tuple[QuestionArchetype, ...]] = {
            BloomLevel.REMEMBER: (
                QuestionArchetype.FACT_RECALL, QuestionArchetype.DEFINITION,
            ),
            BloomLevel.UNDERSTAND: (
                QuestionArchetype.DEFINITION, QuestionArchetype.INFERENCE,
            ),
            BloomLevel.APPLY: (
                QuestionArchetype.APPLICATION, QuestionArchetype.CAUSE_EFFECT,
            ),
            BloomLevel.ANALYZE: (
                QuestionArchetype.COMPARISON, QuestionArchetype.CAUSE_EFFECT,
                QuestionArchetype.ERROR_IDENTIFICATION,
            ),
            BloomLevel.EVALUATE: (
                QuestionArchetype.BEST_STATEMENT, QuestionArchetype.ERROR_IDENTIFICATION,
            ),
        }
        preferred = bloom_map.get(bloom, profile.archetype_pool)
        pool = [a for a in preferred if a in profile.archetype_pool] or list(profile.archetype_pool)
        rng = random.Random(seed + hash(bloom))
        return rng.choice(pool)


# ─── Prompt OpenAI ───────────────────────────────────────────────────────────

OPENAI_SYSTEM_MESSAGE = (
    'Eres un doctor en Ciencias de la Educación y diseñador instruccional experto en '
    'evaluación formativa de alto rigor. Respondes únicamente con JSON válido. '
    'Todo el contenido debe estar en castellano (es-ES). '
    'Cada ítem debe ser pedagógicamente sólido, sin ambigüedades y con una sola respuesta correcta.'
)


class PromptBuilder:
    """Construye prompts multi-sección con marco pedagógico y plan de ítems."""

    def build(self, ctx: GenerationContext, plan: list[QuestionSlot], chunks: list[TextChunk]) -> str:
        profile = ctx.profile
        slot_lines = []
        for slot in plan:
            slot_lines.append(
                f"  - Ítem {slot.order + 1}: bloom={slot.bloom.label_es}, "
                f"dificultad={DIFFICULTY_LABELS_ES.get(slot.difficulty, slot.difficulty)}, "
                f"tipo={slot.archetype.value}, fragmento={slot.chunk.index + 1}"
            )

        excerpt_blocks = []
        for chunk in chunks[: min(len(chunks), ctx.num_questions + 2)]:
            excerpt_blocks.append(
                f"[Fragmento {chunk.index + 1} | relevancia={chunk.score:.1f}]\n"
                f"Conceptos clave: {', '.join(chunk.concepts[:5]) or '—'}\n"
                f"{chunk.text[:1200]}"
            )

        subject_line = ctx.subject or 'No especificada'
        title_line = ctx.activity_title or ctx.material_title or 'Actividad evaluativa'

        return textwrap.dedent(f"""
            ## Encargo de diseño evaluativo
            Diseña exactamente {ctx.num_questions} preguntas de opción múltiple (A–D) de máximo nivel
            académico adaptado al perfil del alumnado.

            ### Contexto
            - Actividad: {title_line}
            - Asignatura / área: {subject_line}
            - Nivel educativo: {profile.label} ({profile.age_range})
            - Dificultad global solicitada: {DIFFICULTY_LABELS_ES.get(ctx.difficulty, ctx.difficulty)}
            - Registro lector: {profile.reading_grade}
            - Tono: {profile.tone_guidance}
            - Vocabulario: {profile.vocabulary_guidance}
            - Longitud máxima enunciado: {profile.max_question_words} palabras
            - Longitud máxima por opción: {profile.max_option_words} palabras

            ### Marco pedagógico (Taxonomía de Bloom revisada)
            Distribución objetivo por ítem:
{chr(10).join(slot_lines)}

            ### Tipos de ítems permitidos
            - definition: definición / significado en contexto
            - fact_recall: dato explícito del texto
            - inference: inferencia fundamentada
            - cause_effect: relación causal o consecuencia
            - comparison: contraste o semejanza
            - application: transferencia a situación nueva
            - best_statement: mejor afirmación según el texto
            - error_identification: detectar la opción incorrecta / falsa

            ### Ingeniería de distractores (obligatorio)
            1. Tres distractores plausibles derivados del mismo fragmento o conceptos relacionados
            2. Evitar "todas las anteriores" / "ninguna de las anteriores"
            3. Longitud similar entre opciones; sin pistas gramaticales
            4. Incluir errores típicos del alumnado (confusión conceptual, generalización indebida)

            ### Rúbrica de calidad (autocomprobación antes de responder)
            ✓ Una sola respuesta inequívocamente correcta según el texto fuente
            ✓ Enunciado autónomo (comprensible sin ver las opciones)
            ✓ Sin negaciones dobles ni trampas capciosas
            ✓ Explicación formativa (2–4 frases) que cite el razonamiento
            ✓ Tema (`topic`) conciso y alineado al currículo implícito del fragmento
            ✓ Variedad de formulaciones; no repetir estructuras

            ### Fragmentos del material fuente
            {"".join(f"---{chr(10)}{block}{chr(10)}" for block in excerpt_blocks)}

            ### Formato de salida
            Responde SOLO con un array JSON. Cada elemento:
            {{
              "text": "Enunciado",
              "option_a": "...", "option_b": "...", "option_c": "...", "option_d": "...",
              "correct_option": "A|B|C|D",
              "explanation": "Retroalimentación formativa",
              "difficulty": "easy|medium|hard",
              "topic": "Tema",
              "source": "fragmento:N|bloom:...|tipo:..."
            }}
            Genera exactamente {ctx.num_questions} objetos en el orden del plan de ítems.
        """).strip()


# ─── API pública ─────────────────────────────────────────────────────────────

def generate_questions(
    text: str,
    num_questions: int = 10,
    difficulty: str = 'medium',
    *,
    education_level: str | None = None,
    subject: str | None = None,
    activity_title: str | None = None,
    material_title: str | None = None,
) -> list[dict]:
    """
    Genera preguntas de opción múltiple a partir de texto fuente.

    Args:
        text: Texto extraído del material didáctico.
        num_questions: Número de ítems (1–50).
        difficulty: easy | medium | hard | mixed.
        education_level: primary | secondary | bachillerato | fp | university | other.
        subject: Asignatura o área curricular.
        activity_title: Título de la actividad (contexto).
        material_title: Título del PDF (contexto).

    Returns:
        Lista de dicts validados listos para persistir como Question.
    """
    ctx = GenerationContext(
        text=text,
        num_questions=num_questions,
        difficulty=difficulty,
        education_level=education_level,
        subject=subject,
        activity_title=activity_title,
        material_title=material_title,
    )

    analyzer = TextAnalyzer()
    planner = AssessmentPlanner()
    chunks = analyzer.analyze(ctx.text)
    plan = planner.build_plan(ctx, chunks)

    api_key = _get_openai_api_key()
    if api_key:
        try:
            questions = _generate_with_openai(ctx, plan, chunks, api_key)
            if questions:
                return QualityGate().finalize(questions, ctx)
            logger.warning('OpenAI devolvió vacío; usando motor heurístico.')
        except Exception as exc:
            logger.error('Fallo OpenAI (%s); usando motor heurístico.', exc)

    questions = _generate_heuristic(ctx, plan)
    return QualityGate().finalize(questions, ctx)


def _get_openai_api_key() -> str | None:
    key = (getattr(settings, 'OPENAI_API_KEY', '') or '').strip()
    if not key or key.startswith('sk-learnleague-dev-placeholder'):
        return None
    return key


def _generate_with_openai(
    ctx: GenerationContext,
    plan: list[QuestionSlot],
    chunks: list[TextChunk],
    api_key: str,
) -> list[dict]:
    from openai import OpenAI

    client = OpenAI(api_key=api_key)
    prompt = PromptBuilder().build(ctx, plan, chunks)

    response = client.chat.completions.create(
        model=getattr(settings, 'OPENAI_MODEL', 'gpt-3.5-turbo'),
        messages=[
            {'role': 'system', 'content': OPENAI_SYSTEM_MESSAGE},
            {'role': 'user', 'content': prompt},
        ],
        temperature=0.55,
        max_tokens=getattr(settings, 'OPENAI_MAX_TOKENS', 4000),
    )

    raw = response.choices[0].message.content.strip()
    raw = re.sub(r'^```(?:json)?\n?', '', raw)
    raw = re.sub(r'\n?```$', '', raw)

    parsed = json.loads(raw)
    if isinstance(parsed, dict):
        for key in ('questions', 'items', 'data'):
            if key in parsed and isinstance(parsed[key], list):
                parsed = parsed[key]
                break
        else:
            parsed = [parsed] if 'text' in parsed else []

    if not isinstance(parsed, list):
        raise ValueError('La respuesta de OpenAI no es un array de preguntas.')

    return _validate_and_clean(parsed, ctx.difficulty)


# ─── Motor heurístico (sin API) ──────────────────────────────────────────────

class HeuristicItemFactory:
    """Sintetiza ítems de calidad a partir del plan y fragmentos analizados."""

    def build(self, ctx: GenerationContext, plan: list[QuestionSlot]) -> list[dict]:
        items: list[dict] = []
        for slot in plan:
            item = self._build_slot(slot, ctx.profile)
            if item:
                items.append(item)
        while len(items) < ctx.num_questions:
            items.append(_generic_question(len(items), ctx.difficulty, ctx.profile))
        return items[:ctx.num_questions]

    def _build_slot(self, slot: QuestionSlot, profile: EducationProfile) -> dict | None:
        builders = {
            QuestionArchetype.FACT_RECALL: self._fact_recall,
            QuestionArchetype.DEFINITION: self._definition,
            QuestionArchetype.INFERENCE: self._inference,
            QuestionArchetype.CAUSE_EFFECT: self._cause_effect,
            QuestionArchetype.COMPARISON: self._comparison,
            QuestionArchetype.APPLICATION: self._application,
            QuestionArchetype.BEST_STATEMENT: self._best_statement,
            QuestionArchetype.ERROR_IDENTIFICATION: self._error_identification,
        }
        builder = builders.get(slot.archetype, self._fact_recall)
        return builder(slot, profile)

    def _pick_sentence(self, chunk: TextChunk) -> str | None:
        if not chunk.sentences:
            return chunk.text[:200] if chunk.text else None
        return max(chunk.sentences, key=len)

    def _pick_concept(self, chunk: TextChunk, sentence: str) -> str | None:
        if chunk.concepts:
            return random.choice(chunk.concepts)
        words = [
            w.rstrip('.,;:') for w in sentence.split()
            if len(w) > 5 and w[0].isupper()
        ]
        return random.choice(words) if words else None

    def _distractors(
        self, chunk: TextChunk, correct: str, n: int = 3,
    ) -> list[str]:
        pool = list({
            w.rstrip('.,;:') for w in chunk.text.split()
            if len(w.rstrip('.,;:')) > 4
            and w.rstrip('.,;:').lower() != correct.lower()
        })
        for c in chunk.concepts:
            if c.lower() != correct.lower():
                pool.append(c)
        random.shuffle(pool)
        distractors = pool[:n]
        fallbacks = [
            'Proceso alternativo', 'Concepto relacionado', 'Hipótesis secundaria',
            'Elemento periférico', 'Interpretación parcial', 'Variable externa',
        ]
        while len(distractors) < n:
            cand = random.choice(fallbacks)
            if cand not in distractors and cand.lower() != correct.lower():
                distractors.append(cand)
        return distractors[:n]

    def _assemble(
        self, slot: QuestionSlot, question_text: str, correct: str,
        distractors: list[str], explanation: str, topic: str,
    ) -> dict:
        options = [correct] + distractors[:3]
        random.shuffle(options)
        letter = chr(ord('A') + options.index(correct))
        return {
            'text': question_text,
            'option_a': options[0],
            'option_b': options[1],
            'option_c': options[2],
            'option_d': options[3],
            'correct_option': letter,
            'explanation': explanation,
            'difficulty': slot.difficulty,
            'topic': topic[:200],
            'source': (
                f"fragmento:{slot.chunk.index + 1}|bloom:{slot.bloom.value}|"
                f"tipo:{slot.archetype.value}"
            ),
            'order': slot.order,
        }

    def _fact_recall(self, slot: QuestionSlot, profile: EducationProfile) -> dict | None:
        sentence = self._pick_sentence(slot.chunk)
        if not sentence:
            return None
        concept = self._pick_concept(slot.chunk, sentence) or 'elemento descrito'
        question = f"Según el texto, ¿qué afirmación se relaciona con «{concept}»?"
        distractors = self._distractors(slot.chunk, concept)
        return self._assemble(
            slot, question, concept, distractors,
            f"El fragmento fuente menciona o desarrolla «{concept}» como elemento central.",
            slot.chunk.concepts[0] if slot.chunk.concepts else _extract_topic(slot.chunk.text),
        )

    def _definition(self, slot: QuestionSlot, profile: EducationProfile) -> dict | None:
        sentence = self._pick_sentence(slot.chunk)
        if not sentence:
            return None
        concept = self._pick_concept(slot.chunk, sentence)
        if not concept:
            return self._fact_recall(slot, profile)
        blanked = sentence.replace(concept, '___', 1)
        question = f"Completa el enunciado: «{blanked}»"
        distractors = self._distractors(slot.chunk, concept)
        return self._assemble(
            slot, question, concept, distractors,
            f"«{concept}» es el término que completa la idea según el material de estudio.",
            concept,
        )

    def _inference(self, slot: QuestionSlot, profile: EducationProfile) -> dict | None:
        sentence = self._pick_sentence(slot.chunk)
        if not sentence or len(sentence) < 40:
            return self._definition(slot, profile)
        concept = self._pick_concept(slot.chunk, sentence) or 'la idea principal'
        question = (
            f"A partir del fragmento, ¿qué se puede inferir sobre «{concept}»?"
        )
        correct = 'Se deduce directamente del contenido del fragmento'
        distractors = [
            'Contradice por completo lo expuesto',
            'No puede inferirse del texto',
            'Es un dato ajeno al tema tratado',
        ]
        return self._assemble(
            slot, question, correct, distractors,
            'La inferencia debe estar fundamentada en información explícita o implícita del texto.',
            _extract_topic(slot.chunk.text),
        )

    def _cause_effect(self, slot: QuestionSlot, profile: EducationProfile) -> dict | None:
        sentence = self._pick_sentence(slot.chunk)
        if not sentence or not _CAUSAL_RE.search(sentence):
            return self._inference(slot, profile)
        concept = self._pick_concept(slot.chunk, sentence) or 'el fenómeno descrito'
        question = f"Según el texto, ¿qué relación causal se establece respecto a «{concept}»?"
        correct = 'Existe una relación de causa y efecto descrita en el fragmento'
        distractors = [
            'No hay relación causal en el fragmento',
            'La relación es puramente temporal sin causalidad',
            'Se presenta como mera coincidencia',
        ]
        return self._assemble(
            slot, question, correct, distractors,
            'El material explicita o sugiere una cadena causa-efecto sobre el concepto tratado.',
            _extract_topic(slot.chunk.text),
        )

    def _comparison(self, slot: QuestionSlot, profile: EducationProfile) -> dict | None:
        if not _COMPARISON_RE.search(slot.chunk.text):
            return self._analyze_fallback(slot, profile)
        question = '¿Qué tipo de relación establece el texto entre los elementos descritos?'
        correct = 'Se contrastan o comparan características relevantes'
        distractors = [
            'Son idénticos en todos los aspectos',
            'No se mencionan juntos en el fragmento',
            'Uno sustituye completamente al otro sin matices',
        ]
        return self._assemble(
            slot, question, correct, distractors,
            'El fragmento contiene marcadores comparativos o de contraste.',
            _extract_topic(slot.chunk.text),
        )

    def _application(self, slot: QuestionSlot, profile: EducationProfile) -> dict | None:
        concept = (slot.chunk.concepts[0] if slot.chunk.concepts else 'el concepto estudiado')
        question = (
            f"En un contexto real de {profile.label.lower()}, "
            f"¿cómo se aplicaría «{concept}» según lo aprendido?"
        )
        correct = 'Siguiendo el procedimiento o principio descrito en el texto'
        distractors = [
            'Ignorando las condiciones descritas en el material',
            'Aplicándolo de forma opuesta a lo indicado',
            'Sin relación con el contenido del fragmento',
        ]
        return self._assemble(
            slot, question, correct, distractors,
            'La aplicación correcta respeta las condiciones y el marco del fragmento fuente.',
            concept,
        )

    def _best_statement(self, slot: QuestionSlot, profile: EducationProfile) -> dict | None:
        sentence = self._pick_sentence(slot.chunk)
        if not sentence:
            return None
        question = '¿Cuál de las siguientes afirmaciones resume mejor el fragmento?'
        correct = sentence[: min(len(sentence), 120)].rstrip('.') + '.'
        distractors = self._distractors(slot.chunk, correct[:20])
        while len(distractors) < 3:
            distractors.append('Afirmación no respaldada por el texto')
        return self._assemble(
            slot, question, correct, distractors[:3],
            'La opción correcta sintetiza fielmente la idea principal del fragmento.',
            _extract_topic(slot.chunk.text),
        )

    def _error_identification(self, slot: QuestionSlot, profile: EducationProfile) -> dict | None:
        concept = self._pick_concept(slot.chunk, slot.chunk.text) or 'el tema'
        question = f"¿Qué afirmación sobre «{concept}» NO es coherente con el texto?"
        correct = 'Contradice o distorsiona lo expuesto en el fragmento'
        distractors = [
            'Resume correctamente una idea del fragmento',
            'Parafrasea fielmente el contenido',
            'Refleja una consecuencia descrita en el texto',
        ]
        return self._assemble(
            slot, question, correct, distractors,
            'La respuesta correcta identifica la opción incompatible con el material fuente.',
            concept,
        )

    def _analyze_fallback(self, slot: QuestionSlot, profile: EducationProfile) -> dict | None:
        return self._inference(slot, profile)


def _generate_heuristic(ctx: GenerationContext, plan: list[QuestionSlot]) -> list[dict]:
    return HeuristicItemFactory().build(ctx, plan)


# ─── Control de calidad ──────────────────────────────────────────────────────

class QualityGate:
    """Post-procesado: deduplicación, equilibrio de claves y recorte."""

    def finalize(self, questions: list[dict], ctx: GenerationContext) -> list[dict]:
        cleaned = _validate_and_clean(questions, ctx.difficulty)
        cleaned = self._deduplicate(cleaned)
        cleaned = self._balance_correct_options(cleaned)
        if len(cleaned) < ctx.num_questions:
            profile = ctx.profile
            while len(cleaned) < ctx.num_questions:
                cleaned.append(_generic_question(len(cleaned), ctx.difficulty, profile))
        return cleaned[:ctx.num_questions]

    def _deduplicate(self, questions: list[dict]) -> list[dict]:
        seen: set[str] = set()
        unique: list[dict] = []
        for q in questions:
            key = re.sub(r'\s+', ' ', q['text'].lower())[:120]
            if key not in seen:
                seen.add(key)
                unique.append(q)
        return unique

    def _balance_correct_options(self, questions: list[dict]) -> list[dict]:
        """Evita sesgo hacia una misma letra correcta cuando hay ≥4 ítems."""
        if len(questions) < 4:
            return questions
        letters = [q['correct_option'] for q in questions]
        if len(set(letters)) <= 1:
            target_cycle = ['A', 'B', 'C', 'D']
            for i, q in enumerate(questions):
                desired = target_cycle[i % 4]
                if q['correct_option'] != desired:
                    self._rotate_correct_to(q, desired)
        return questions

    def _rotate_correct_to(self, question: dict, target: str) -> None:
        opts = {
            'A': question['option_a'],
            'B': question['option_b'],
            'C': question['option_c'],
            'D': question['option_d'],
        }
        current = question['correct_option']
        if current not in opts or target not in opts:
            return
        correct_text = opts[current]
        opts[current], opts[target] = opts[target], opts[current]
        question['option_a'] = opts['A']
        question['option_b'] = opts['B']
        question['option_c'] = opts['C']
        question['option_d'] = opts['D']
        question['correct_option'] = target
        if correct_text != opts[target]:
            question['correct_option'] = next(
                k for k, v in opts.items() if v == correct_text
            )


# ─── Utilidades ──────────────────────────────────────────────────────────────

def _extract_topic(text: str) -> str:
    first_line = text.split('\n')[0].strip()
    if len(first_line) <= 60:
        return first_line
    words = [w for w in first_line.split() if len(w) > 3]
    return ' '.join(words[:5]) if words else 'Tema general'


def _generic_question(index: int, difficulty: str, profile: EducationProfile) -> dict:
    templates = [
        {
            'text': f'¿Cuál es un objetivo formativo clave en {profile.label}?',
            'option_a': 'Comprender, aplicar y transferir aprendizajes significativos',
            'option_b': 'Memorizar datos aislados sin contexto',
            'option_c': 'Repetir información sin verificar comprensión',
            'option_d': 'Evitar toda actividad de reflexión crítica',
            'correct_option': 'A',
            'explanation': (
                'Un diseño evaluativo de calidad prioriza comprensión profunda '
                'y transferencia, especialmente en ' + profile.label + '.'
            ),
            'difficulty': difficulty if difficulty != 'mixed' else 'medium',
            'topic': profile.label,
            'source': 'fallback:generic',
        },
        {
            'text': '¿Qué caracteriza a una pregunta de opción múltiple bien diseñada?',
            'option_a': 'Enunciado claro, una sola respuesta correcta y distractores plausibles',
            'option_b': 'Enunciado ambiguo con varias respuestas posibles',
            'option_c': 'Opciones de longitud muy desigual que dan pistas',
            'option_d': 'Ausencia total de retroalimentación',
            'correct_option': 'A',
            'explanation': (
                'La validez del ítem exige claridad, unicidad de respuesta '
                'y distractores que reflejen errores conceptuales reales.'
            ),
            'difficulty': difficulty if difficulty != 'mixed' else 'medium',
            'topic': 'Diseño de ítems',
            'source': 'fallback:generic',
        },
    ]
    q = templates[index % len(templates)].copy()
    q['order'] = index
    return q


def _validate_and_clean(questions: list, default_difficulty: str) -> list[dict]:
    required = {'text', 'option_a', 'option_b', 'option_c', 'option_d', 'correct_option'}
    valid: list[dict] = []

    for i, q in enumerate(questions):
        if not isinstance(q, dict):
            continue
        if not required.issubset(q.keys()):
            logger.warning('Ítem %d: faltan campos obligatorios.', i)
            continue
        letter = str(q['correct_option']).upper()
        if letter not in VALID_OPTIONS:
            logger.warning('Ítem %d: correct_option inválida.', i)
            continue
        diff = q.get('difficulty', default_difficulty)
        if diff not in DIFFICULTY_LEVELS - {'mixed'}:
            diff = default_difficulty if default_difficulty != 'mixed' else 'medium'

        valid.append({
            'text': str(q['text'])[:2000],
            'option_a': str(q['option_a'])[:500],
            'option_b': str(q['option_b'])[:500],
            'option_c': str(q['option_c'])[:500],
            'option_d': str(q['option_d'])[:500],
            'correct_option': letter,
            'explanation': str(q.get('explanation', ''))[:1000],
            'difficulty': diff,
            'topic': str(q.get('topic', ''))[:200],
            'source': str(q.get('source', ''))[:300],
            'order': i,
        })

    return valid
