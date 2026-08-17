"""
Management command: seed_data

Creates a complete demo dataset for development and testing:
  - 1 teacher account
  - 2 classrooms
  - 2 teaching materials (with extracted text)
  - 2 activities with 10 questions each
  - 1 finished game session with 5 players and all answers

Usage:
    python manage.py seed_data
    python manage.py seed_data --clear      (deletes existing demo data first)
"""
import os
import random
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone

User = get_user_model()

TEACHER_EMAIL = 'teacher@learnleague.demo'
TEACHER_PASSWORD = 'Demo1234!'

MATH_TEXT = """
Algebra is a branch of mathematics dealing with symbols and the rules for manipulating those symbols.
In elementary algebra, those symbols represent quantities without fixed values, known as variables.

The quadratic formula is used to solve second-degree polynomial equations of the form ax² + bx + c = 0.
The solution is: x = (-b ± √(b²-4ac)) / 2a. The discriminant (b²-4ac) determines the number of solutions:
if positive, there are two real solutions; if zero, one real solution; if negative, two complex solutions.

Functions are fundamental in mathematics. A function f maps each element of a set X to exactly one element
of a set Y. The domain is the set of input values, and the range is the set of output values.

The Pythagorean theorem states that in a right triangle, the square of the hypotenuse equals the sum
of squares of the other two sides: a² + b² = c². This theorem is fundamental to Euclidean geometry.

Statistics involves collecting, analyzing, interpreting, and presenting data. Measures of central tendency
include the mean (arithmetic average), median (middle value), and mode (most frequent value).
The standard deviation measures how spread out the numbers in a dataset are from the mean.

Probability is the measure of the likelihood that an event will occur. It ranges from 0 (impossible)
to 1 (certain). The probability of two independent events both occurring is the product of their
individual probabilities. Conditional probability P(A|B) is the probability of event A given that B has occurred.

Linear equations represent straight lines when graphed. Two variables x and y satisfy a linear equation
of the form y = mx + b, where m is the slope and b is the y-intercept.
The slope indicates the rate of change between variables.

Matrices are rectangular arrays of numbers used in linear algebra to represent linear transformations.
Matrix multiplication is not commutative (AB ≠ BA). The determinant of a square matrix determines
whether the matrix is invertible. The identity matrix has ones on the diagonal and zeros elsewhere.
"""

HISTORY_TEXT = """
The French Revolution (1789-1799) was a period of radical political and societal transformation in France.
It began with a financial crisis and social inequality under King Louis XVI. The revolution culminated in
the abolition of the monarchy and the rise of Napoleon Bonaparte.

The Declaration of the Rights of Man and of the Citizen (1789) established fundamental rights including
liberty, property, security, and resistance to oppression. This document became one of the foundational
texts of human rights and democracy worldwide.

The Industrial Revolution began in Great Britain during the late 18th century and transformed manufacturing
processes from hand production to machine-based production. Key innovations included the steam engine,
the spinning jenny, and mechanized textile production. This shift had profound social consequences.

World War I (1914-1918) was a global conflict centered in Europe. It began following the assassination
of Archduke Franz Ferdinand of Austria. The war introduced new military technologies including tanks,
chemical weapons, and aerial combat. Over 17 million people lost their lives in the conflict.

The Renaissance was a cultural movement that began in Florence, Italy, during the 14th century.
It was characterized by renewed interest in classical Greek and Roman art, architecture, and learning.
Key figures included Leonardo da Vinci, Michelangelo, and Raphael. The printing press, invented by
Johannes Gutenberg around 1440, helped spread Renaissance ideas throughout Europe.

The Cold War (1947-1991) was a geopolitical tension between the United States and the Soviet Union.
It was characterized by nuclear arms race, proxy wars, and ideological competition between capitalism
and communism. The Berlin Wall, built in 1961, became the most iconic symbol of the Cold War.
The dissolution of the Soviet Union in 1991 marked the end of this era.

Ancient Rome built an empire that at its peak covered much of Europe, North Africa, and parts of Asia.
Roman contributions to civilization include their legal system, architecture (aqueducts, roads),
the Latin language, and the spread of Christianity throughout the empire.
"""

MATH_QUESTIONS = [
    {
        'text': 'What does the discriminant (b²-4ac) tell us about a quadratic equation?',
        'option_a': 'The number of solutions the equation has',
        'option_b': 'The sum of all solutions',
        'option_c': 'The product of all solutions',
        'option_d': 'The degree of the polynomial',
        'correct_option': 'A',
        'explanation': 'The discriminant determines the number of real solutions: positive = 2, zero = 1, negative = 0 (complex).',
        'difficulty': 'medium',
        'topic': 'Quadratic Equations',
    },
    {
        'text': 'In the equation y = mx + b, what does "m" represent?',
        'option_a': 'The y-intercept',
        'option_b': 'The slope (rate of change)',
        'option_c': 'The x-intercept',
        'option_d': 'The domain of the function',
        'correct_option': 'B',
        'explanation': 'm represents the slope, indicating the rate of change between x and y values.',
        'difficulty': 'easy',
        'topic': 'Linear Equations',
    },
    {
        'text': 'According to the Pythagorean theorem, if a=3 and b=4, what is c?',
        'option_a': '7',
        'option_b': '6',
        'option_c': '5',
        'option_d': '12',
        'correct_option': 'C',
        'explanation': 'c = √(a² + b²) = √(9 + 16) = √25 = 5.',
        'difficulty': 'easy',
        'topic': 'Geometry',
    },
    {
        'text': 'What is the range in a set of data?',
        'option_a': 'The most frequently occurring value',
        'option_b': 'The middle value when sorted',
        'option_c': 'The arithmetic average of all values',
        'option_d': 'The difference between the highest and lowest values',
        'correct_option': 'D',
        'explanation': 'The range is calculated as maximum value minus minimum value.',
        'difficulty': 'easy',
        'topic': 'Statistics',
    },
    {
        'text': 'What is the probability of getting heads on a fair coin twice in a row?',
        'option_a': '1/2',
        'option_b': '1/3',
        'option_c': '1/4',
        'option_d': '1/8',
        'correct_option': 'C',
        'explanation': 'P(H) × P(H) = 0.5 × 0.5 = 0.25 = 1/4 for independent events.',
        'difficulty': 'medium',
        'topic': 'Probability',
    },
    {
        'text': 'What does it mean for a matrix to be "invertible"?',
        'option_a': 'It has more rows than columns',
        'option_b': 'Its determinant is non-zero',
        'option_c': 'All its values are positive',
        'option_d': 'It is a square matrix',
        'correct_option': 'B',
        'explanation': 'A matrix is invertible if and only if its determinant is non-zero.',
        'difficulty': 'hard',
        'topic': 'Linear Algebra',
    },
    {
        'text': 'Which of the following is a property of functions?',
        'option_a': 'Each input can map to multiple outputs',
        'option_b': 'Each output must have exactly one input',
        'option_c': 'Each input maps to exactly one output',
        'option_d': 'The domain and range must be equal sets',
        'correct_option': 'C',
        'explanation': 'By definition, a function maps each element of its domain to exactly one element in the range.',
        'difficulty': 'medium',
        'topic': 'Functions',
    },
    {
        'text': 'What is the standard deviation used to measure?',
        'option_a': 'The most common value in a dataset',
        'option_b': 'How spread out values are from the mean',
        'option_c': 'The total sum of all values',
        'option_d': 'The middle value of a sorted dataset',
        'correct_option': 'B',
        'explanation': 'Standard deviation measures the amount of variation or dispersion of values from the mean.',
        'difficulty': 'medium',
        'topic': 'Statistics',
    },
    {
        'text': 'Is matrix multiplication commutative?',
        'option_a': 'Yes, always AB = BA',
        'option_b': 'Only for square matrices',
        'option_c': 'No, generally AB ≠ BA',
        'option_d': 'Only for identity matrices',
        'correct_option': 'C',
        'explanation': 'Matrix multiplication is not commutative; the order of multiplication matters.',
        'difficulty': 'medium',
        'topic': 'Linear Algebra',
    },
    {
        'text': 'In algebra, what are variables?',
        'option_a': 'Fixed numerical constants',
        'option_b': 'Symbols representing quantities without fixed values',
        'option_c': 'Operations between numbers',
        'option_d': 'Solutions to equations',
        'correct_option': 'B',
        'explanation': 'Variables are symbols that represent unknown or changing quantities.',
        'difficulty': 'easy',
        'topic': 'Algebra Basics',
    },
]

HISTORY_QUESTIONS = [
    {
        'text': 'What event triggered the start of World War I?',
        'option_a': 'The invasion of Poland by Germany',
        'option_b': 'The assassination of Archduke Franz Ferdinand',
        'option_c': 'The signing of the Treaty of Versailles',
        'option_d': 'The Russian Revolution',
        'correct_option': 'B',
        'explanation': 'WWI began following the assassination of Archduke Franz Ferdinand of Austria in 1914.',
        'difficulty': 'medium',
        'topic': 'World War I',
    },
    {
        'text': 'Where did the Renaissance cultural movement begin?',
        'option_a': 'Rome, Italy',
        'option_b': 'Paris, France',
        'option_c': 'Florence, Italy',
        'option_d': 'Athens, Greece',
        'correct_option': 'C',
        'explanation': 'The Renaissance began in Florence, Italy, during the 14th century.',
        'difficulty': 'easy',
        'topic': 'Renaissance',
    },
    {
        'text': 'What symbol became most iconic during the Cold War?',
        'option_a': 'The Eiffel Tower',
        'option_b': 'The Berlin Wall',
        'option_c': 'The Iron Curtain',
        'option_d': 'The Statue of Liberty',
        'correct_option': 'B',
        'explanation': 'The Berlin Wall, built in 1961, became the most iconic symbol of the Cold War division.',
        'difficulty': 'easy',
        'topic': 'Cold War',
    },
    {
        'text': 'Which invention helped spread Renaissance ideas throughout Europe?',
        'option_a': 'The telescope',
        'option_b': 'The steam engine',
        'option_c': 'The printing press',
        'option_d': 'The compass',
        'correct_option': 'C',
        'explanation': 'The printing press, invented by Gutenberg around 1440, enabled mass production of books.',
        'difficulty': 'medium',
        'topic': 'Renaissance',
    },
    {
        'text': 'When did the French Revolution begin?',
        'option_a': '1776',
        'option_b': '1789',
        'option_c': '1804',
        'option_d': '1815',
        'correct_option': 'B',
        'explanation': 'The French Revolution began in 1789 with financial crisis and social inequality under Louis XVI.',
        'difficulty': 'easy',
        'topic': 'French Revolution',
    },
    {
        'text': 'What was a key social consequence of the Industrial Revolution?',
        'option_a': 'Decline in urbanization',
        'option_b': 'Return to agrarian society',
        'option_c': 'Shift from hand production to machine manufacturing',
        'option_d': 'Reduction in international trade',
        'correct_option': 'C',
        'explanation': 'The Industrial Revolution transformed manufacturing from artisan methods to mechanized factory production.',
        'difficulty': 'medium',
        'topic': 'Industrial Revolution',
    },
    {
        'text': 'How many people approximately lost their lives in World War I?',
        'option_a': '1 million',
        'option_b': '5 million',
        'option_c': '17 million',
        'option_d': '40 million',
        'correct_option': 'C',
        'explanation': 'Over 17 million people died in WWI, making it one of history\'s deadliest conflicts.',
        'difficulty': 'hard',
        'topic': 'World War I',
    },
    {
        'text': 'What did the Declaration of the Rights of Man establish?',
        'option_a': 'France\'s constitutional monarchy',
        'option_b': 'The power of Napoleon Bonaparte',
        'option_c': 'Fundamental rights including liberty and property',
        'option_d': 'The abolition of the French senate',
        'correct_option': 'C',
        'explanation': 'The Declaration established fundamental rights: liberty, property, security, and resistance to oppression.',
        'difficulty': 'medium',
        'topic': 'French Revolution',
    },
    {
        'text': 'When did the Cold War officially end?',
        'option_a': '1989',
        'option_b': '1991',
        'option_c': '1995',
        'option_d': '1985',
        'correct_option': 'B',
        'explanation': 'The dissolution of the Soviet Union in 1991 marked the end of the Cold War.',
        'difficulty': 'medium',
        'topic': 'Cold War',
    },
    {
        'text': 'Which country began the Industrial Revolution?',
        'option_a': 'France',
        'option_b': 'Germany',
        'option_c': 'United States',
        'option_d': 'Great Britain',
        'correct_option': 'D',
        'explanation': 'The Industrial Revolution began in Great Britain during the late 18th century.',
        'difficulty': 'easy',
        'topic': 'Industrial Revolution',
    },
]

PLAYER_ALIASES = ['Kronos', 'Viper', 'Blaze', 'Nova', 'Pixel']
PLAYER_AVATARS = ['🦊', '🐺', '🦁', '🐯', '🐸']


class Command(BaseCommand):
    help = 'Seed the database with demo data for LearnLeague.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Delete existing demo data before seeding.',
        )

    def handle(self, *args, **options):
        # Allow deployments to opt-out of demo data by setting SEED_DEMO_DATA=false
        # in Heroku config vars.  Defaults to "true" for backward compatibility.
        if os.environ.get('SEED_DEMO_DATA', 'true').lower() == 'false':
            self.stdout.write('SEED_DEMO_DATA=false — skipping demo data seed.')
            return

        if options['clear']:
            self._clear_demo_data()

        self.stdout.write('Seeding demo data...')

        teacher = self._create_teacher()
        classroom_math, classroom_history = self._create_classrooms(teacher)
        material_math, material_history = self._create_materials(teacher, classroom_math, classroom_history)
        activity_math, activity_history = self._create_activities(
            teacher, classroom_math, classroom_history, material_math, material_history
        )
        self._create_game_session(teacher, activity_math, classroom_math)

        self.stdout.write(self.style.SUCCESS(
            '\nDemo data seeded successfully!\n'
            f'   Teacher login: {TEACHER_EMAIL} / {TEACHER_PASSWORD}\n'
        ))

    def _clear_demo_data(self):
        self.stdout.write('Clearing existing demo data...')
        User.objects.filter(email=TEACHER_EMAIL).delete()
        self.stdout.write('   Cleared.')

    def _create_teacher(self):
        from apps.accounts.models import User as UserModel
        user, created = UserModel.objects.get_or_create(
            email=TEACHER_EMAIL,
            defaults={
                'username': 'demo_teacher',
                'first_name': 'María',
                'last_name': 'García',
                'role': 'teacher',
                'school': 'IES Cervantes',
                'subject_specialty': 'Mathematics & History',
                'bio': 'Passionate educator with 10 years of experience.',
            },
        )
        if created:
            user.set_password(TEACHER_PASSWORD)
            user.save()
            self.stdout.write(f'   ✓ Teacher created: {TEACHER_EMAIL}')
        else:
            self.stdout.write(f'   ~ Teacher already exists: {TEACHER_EMAIL}')
        return user

    def _create_classrooms(self, teacher):
        from apps.classes.models import ClassRoom
        math_class = ClassRoom.objects.filter(name='Matemáticas 1°ESO', teacher=teacher).first()
        if not math_class:
            math_class = ClassRoom.objects.create(
                name='Matemáticas 1°ESO', teacher=teacher,
                subject='Mathematics', education_level='secondary',
                description='First year secondary school mathematics class.',
                color='#6366f1',
            )
        history_class = ClassRoom.objects.filter(name='Historia 2°Bachillerato', teacher=teacher).first()
        if not history_class:
            history_class = ClassRoom.objects.create(
                name='Historia 2°Bachillerato', teacher=teacher,
                subject='History', education_level='bachillerato',
                description='Pre-university history of the modern world.',
                color='#f59e0b',
            )
        self.stdout.write('   ✓ Classrooms created.')
        return math_class, history_class

    def _create_materials(self, teacher, math_class, history_class):
        from apps.materials.models import TeachingMaterial
        # Use filter().first() to tolerate any pre-existing duplicate rows
        math_mat = TeachingMaterial.objects.filter(
            title='Introduction to Algebra and Statistics', teacher=teacher
        ).first()
        if not math_mat:
            math_mat = TeachingMaterial.objects.create(
                title='Introduction to Algebra and Statistics', teacher=teacher,
                classroom=math_class, status='completed',
                extracted_text=MATH_TEXT, page_count=12, file_size=524288,
            )
        history_mat = TeachingMaterial.objects.filter(
            title='Modern World History: Revolution to Cold War', teacher=teacher
        ).first()
        if not history_mat:
            history_mat = TeachingMaterial.objects.create(
                title='Modern World History: Revolution to Cold War', teacher=teacher,
                classroom=history_class, status='completed',
                extracted_text=HISTORY_TEXT, page_count=18, file_size=786432,
            )
        self.stdout.write('   ✓ Teaching materials created.')
        return math_mat, history_mat

    def _create_activities(self, teacher, math_class, history_class, math_mat, history_mat):
        from apps.activities.models import Activity, Question
        math_act = Activity.objects.filter(title='Algebra & Statistics Quiz', teacher=teacher).first()
        if not math_act:
            math_act = Activity.objects.create(
                title='Algebra & Statistics Quiz', teacher=teacher,
                classroom=math_class, material=math_mat,
                status='ready', time_per_question=30,
                description='Test your knowledge of algebra, geometry, and statistics.',
            )
            for i, q_data in enumerate(MATH_QUESTIONS):
                Question.objects.create(activity=math_act, order=i, **q_data)

        history_act = Activity.objects.filter(title='Modern History Quiz', teacher=teacher).first()
        if not history_act:
            history_act = Activity.objects.create(
                title='Modern History Quiz', teacher=teacher,
                classroom=history_class, material=history_mat,
                status='ready', time_per_question=35,
                description='Test your knowledge of modern history from the Renaissance to the Cold War.',
            )
            for i, q_data in enumerate(HISTORY_QUESTIONS):
                Question.objects.create(activity=history_act, order=i, **q_data)

        self.stdout.write('   ✓ Activities with 10 questions each created.')
        return math_act, history_act

    def _create_game_session(self, teacher, activity, classroom):
        from apps.games.models import GameSession, Player, Answer
        from apps.activities.models import Question

        now = timezone.now()
        session = GameSession.objects.filter(activity=activity, teacher=teacher, status='finished').first()
        if session:
            self.stdout.write('   ~ Demo game session already exists.')
            return

        session = GameSession.objects.create(
            activity=activity, teacher=teacher, status='finished',
            classroom=classroom, code='DEMO01',
            started_at=now - timedelta(hours=1),
            finished_at=now - timedelta(minutes=30),
            current_question_index=10,
        )

        questions = list(activity.questions.order_by('order'))
        time_limit = activity.time_per_question

        # Create 5 players with varying performance
        players = []
        for i, (alias, avatar) in enumerate(zip(PLAYER_ALIASES, PLAYER_AVATARS)):
            player = Player.objects.create(
                session=session,
                alias=alias,
                avatar=avatar,
            )
            players.append(player)

        # Each player answers all questions
        for i, player in enumerate(players):
            # Performance degrades for lower-ranked players
            accuracy_rate = 0.9 - (i * 0.15)  # 90%, 75%, 60%, 45%, 30%
            total_score = 0
            total_correct = 0
            total_answers = 0
            response_times = []

            for j, question in enumerate(questions):
                is_correct = random.random() < accuracy_rate
                response_time = round(random.uniform(3.0, time_limit * 0.9), 2)

                if is_correct:
                    speed_ratio = max(0.0, 1.0 - (response_time / time_limit))
                    points = 100 + int(50 * speed_ratio)
                    total_correct += 1
                else:
                    points = 0

                selected = question.correct_option if is_correct else random.choice(
                    [o for o in ('A', 'B', 'C', 'D') if o != question.correct_option]
                )

                Answer.objects.create(
                    player=player,
                    question=question,
                    selected_option=selected,
                    is_correct=is_correct,
                    response_time=response_time,
                    points=points,
                )

                total_score += points
                total_answers += 1
                response_times.append(response_time)

            avg_rt = sum(response_times) / len(response_times) if response_times else 0
            player.score = total_score
            player.correct_answers = total_correct
            player.total_answers = total_answers
            player.avg_response_time = round(avg_rt, 2)
            player.save(update_fields=['score', 'correct_answers', 'total_answers', 'avg_response_time'])

        activity.status = 'played'
        activity.save(update_fields=['status'])

        self.stdout.write(
            f'   ✓ Demo game session "{session.code}" created with 5 players and {len(questions) * 5} answers.'
        )
