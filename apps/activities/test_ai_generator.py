"""Tests for the academic question generation engine."""
import pytest

from apps.activities.ai_generator import (
    AssessmentPlanner,
    BloomLevel,
    GenerationContext,
    TextAnalyzer,
    generate_questions,
)


class TestTextAnalyzer:
    def test_scores_definition_heavy_paragraph_higher(self):
        analyzer = TextAnalyzer()
        plain = 'El sol brilla. Los niños juegan en el parque durante la tarde.'
        rich = (
            'La fotosíntesis es el proceso mediante el cual las plantas convierten '
            'la luz solar en energía química. Por consiguiente, produce oxígeno '
            'como subproducto esencial para la respiración aeróbica.'
        )
        score_plain = analyzer.analyze(plain)[0].score if analyzer.analyze(plain) else 0
        score_rich = analyzer.analyze(rich)[0].score
        assert score_rich > score_plain

    def test_extracts_concepts(self):
        analyzer = TextAnalyzer()
        text = (
            'La Mitocondria es la organela responsable de la respiración celular. '
            'El ATP almacena energía utilizable por la célula.'
        )
        chunks = analyzer.analyze(text)
        assert chunks
        assert any(c.concepts for c in chunks)


class TestAssessmentPlanner:
    def test_primary_skews_remember_understand(self):
        ctx = GenerationContext(
            text='Texto de prueba ' * 50,
            num_questions=10,
            education_level='primary',
        )
        plan = AssessmentPlanner().build_plan(ctx, TextAnalyzer().analyze(ctx.text))
        blooms = [slot.bloom for slot in plan]
        assert blooms.count(BloomLevel.REMEMBER) + blooms.count(BloomLevel.UNDERSTAND) >= 6

    def test_university_includes_analyze_evaluate(self):
        ctx = GenerationContext(
            text='Texto universitario ' * 50,
            num_questions=10,
            education_level='university',
        )
        plan = AssessmentPlanner().build_plan(ctx, TextAnalyzer().analyze(ctx.text))
        blooms = {slot.bloom for slot in plan}
        assert BloomLevel.ANALYZE in blooms or BloomLevel.EVALUATE in blooms

    def test_mixed_difficulty_schedule(self):
        ctx = GenerationContext(
            text='Contenido ' * 80,
            num_questions=9,
            difficulty='mixed',
        )
        plan = AssessmentPlanner().build_plan(ctx, TextAnalyzer().analyze(ctx.text))
        diffs = {slot.difficulty for slot in plan}
        assert diffs == {'easy', 'medium', 'hard'}


@pytest.mark.django_db
class TestGenerateQuestions:
    def test_generates_spanish_heuristic_items(self):
        text = (
            'La Revolución Industrial fue un periodo de transformación económica '
            'porque introdujo la mecanización en la producción textil. '
            'Sin embargo, también generó condiciones de trabajo difíciles en las fábricas. '
            'El vapor, inventado por Watt, impulsó nuevas formas de transporte.'
        )
        items = generate_questions(
            text,
            num_questions=5,
            difficulty='medium',
            education_level='secondary',
            subject='Historia',
        )
        assert len(items) == 5
        assert all('text' in q and q['correct_option'] in {'A', 'B', 'C', 'D'} for q in items)
        assert any('fragmento:' in q.get('source', '') for q in items)

    def test_respects_education_level_profile(self):
        primary = generate_questions(
            'La fotosíntesis es el proceso por el cual las plantas producen alimento.',
            num_questions=3,
            education_level='primary',
        )
        university = generate_questions(
            'La fotosíntesis es el proceso por el cual las plantas producen alimento.',
            num_questions=3,
            education_level='university',
        )
        assert len(primary) == len(university) == 3
