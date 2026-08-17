#!/usr/bin/env python
"""
Convenience script to run the seed_data management command.
Run from the backend directory: python scripts/seed_data.py
"""
import os
import sys

if __name__ == '__main__':
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development')
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    import django
    django.setup()

    from django.core.management import call_command
    call_command('seed_data', *sys.argv[1:])
