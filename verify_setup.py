#!/usr/bin/env python3
"""
GeoIntel Setup Verification Script
Checks that all components are properly configured before starting
"""

import os
import sys
import json

def check_python_version():
    """Verify Python 3.8+"""
    version = sys.version_info
    if version.major < 3 or (version.major == 3 and version.minor < 8):
        print(f"❌ Python 3.8+ required (you have {version.major}.{version.minor})")
        return False
    print(f"✅ Python version: {version.major}.{version.minor}.{version.micro}")
    return True

def check_files():
    """Verify all required files exist"""
    required_files = {
        'frontend': [
            'index.html',
            'frontend-api.js',
            'topojson.min.js',
            'countries-110m.json',
        ],
        'backend': [
            'backend/app.py',
            'backend/models.py',
            'backend/data_sources.py',
            'backend/requirements.txt',
            'backend/.env',
        ]
    }

    all_good = True
    for location, files in required_files.items():
        print(f"\n{location.upper()} FILES:")
        for file in files:
            if os.path.exists(file):
                size = os.path.getsize(file)
                print(f"  ✅ {file:<40} ({size:,} bytes)")
            else:
                print(f"  ❌ {file:<40} MISSING")
                all_good = False

    return all_good

def check_dependencies():
    """Check if required Python packages are installed"""
    required_packages = {
        'flask': 'Flask',
        'flask_cors': 'Flask-CORS',
        'sqlalchemy': 'SQLAlchemy',
        'requests': 'requests',
        'apscheduler': 'APScheduler',
        'textblob': 'TextBlob',
        'dotenv': 'python-dotenv',
    }

    print("\nPYTHON DEPENDENCIES:")
    all_installed = True

    for import_name, package_name in required_packages.items():
        try:
            __import__(import_name)
            print(f"  ✅ {package_name:<25} installed")
        except ImportError:
            print(f"  ❌ {package_name:<25} NOT installed")
            all_installed = False

    if not all_installed:
        print("\n  Run: pip install -r backend/requirements.txt")

    return all_installed

def check_env_config():
    """Check .env configuration"""
    print("\nBACKEND CONFIGURATION (.env):")
    env_path = 'backend/.env'

    if not os.path.exists(env_path):
        print(f"  ❌ {env_path} not found")
        return False

    # Read .env
    config = {}
    with open(env_path, 'r') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#'):
                if '=' in line:
                    key, val = line.split('=', 1)
                    config[key.strip()] = val.strip()

    # Check required settings
    checks = {
        'NEWSAPI_KEY': 'NewsAPI key',
        'DATABASE_URL': 'Database URL',
        'FLASK_ENV': 'Flask environment',
    }

    all_good = True
    for key, desc in checks.items():
        if key in config:
            val = config[key]
            if val.startswith('your_') or val == '':
                print(f"  ⚠️  {desc:<25} needs configuration")
                all_good = False
            else:
                print(f"  ✅ {desc:<25} configured")
        else:
            print(f"  ❌ {desc:<25} missing")
            all_good = False

    if not all_good:
        print(f"\n  Edit {env_path} and add:")
        print(f"  - NEWSAPI_KEY from https://newsapi.org")

    return all_good

def check_database():
    """Check if database is initialized"""
    print("\nDATABASE:")
    db_path = 'backend/geointel.db'

    if os.path.exists(db_path):
        size = os.path.getsize(db_path)
        print(f"  ✅ Database exists ({size:,} bytes)")
        return True
    else:
        print(f"  ⚠️  Database not initialized")
        print(f"     Run: cd backend && python models.py")
        return False

def check_backend_running():
    """Test if backend API is running"""
    print("\nBACKEND API:")
    try:
        import requests
        response = requests.get('http://localhost:5000/api/health', timeout=2)
        if response.status_code == 200:
            data = response.json()
            if data.get('status') == 'ok':
                print(f"  ✅ Backend is running")
                print(f"     Version: {data.get('version', 'unknown')}")
                return True
    except Exception as e:
        pass

    print(f"  ⚠️  Backend not running at http://localhost:5000")
    print(f"     Run: cd backend && python app.py")
    return False

def main():
    print("\n" + "="*60)
    print("GeoIntel Platform - Setup Verification")
    print("="*60)

    results = {
        'Python Version': check_python_version(),
        'Required Files': check_files(),
        'Dependencies': check_dependencies(),
        'Configuration': check_env_config(),
        'Database': check_database(),
        'Backend Running': check_backend_running(),
    }

    print("\n" + "="*60)
    print("SUMMARY:")
    print("="*60)

    for check, passed in results.items():
        status = "✅ READY" if passed else "⚠️  NEEDS ATTENTION"
        print(f"  {status:<20} {check}")

    all_passed = all(results.values())

    print("\n" + "="*60)
    if all_passed:
        print("✅ ALL CHECKS PASSED - Platform is ready!")
        print("\nYou can now:")
        print("  1. Open index.html in your browser")
        print("  2. See real data from ACLED, NewsAPI, World Bank")
        print("  3. Explore geopolitical crises on the interactive globe")
    else:
        print("⚠️  SOME CHECKS FAILED - See above for fixes")
        print("\nNext steps:")
        print("  1. Install dependencies: pip install -r backend/requirements.txt")
        print("  2. Get NewsAPI key: https://newsapi.org")
        print("  3. Initialize database: cd backend && python models.py")
        print("  4. Run backend: cd backend && python app.py")

    print("="*60 + "\n")

    return 0 if all_passed else 1

if __name__ == '__main__':
    sys.exit(main())
