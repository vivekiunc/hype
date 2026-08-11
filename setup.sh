#!/bin/bash
# Quick setup script for Oracle Latency Arbitrage research framework

set -e

echo "=== Oracle Latency Arbitrage Research Setup ==="
echo

# Check Python version
python_version=$(python3 --version 2>&1 | awk '{print $2}')
echo "✓ Python version: $python_version"

# Install dependencies
echo "Installing Python dependencies..."
pip install -q -r requirements.txt
echo "✓ Dependencies installed"

# Copy .env
if [ ! -f .env ]; then
    echo "Creating .env file from template..."
    cp .env.example .env
    echo "✓ .env created (edit with your database credentials)"
else
    echo "✓ .env already exists"
fi

# Check PostgreSQL
echo
echo "Checking PostgreSQL installation..."
if command -v psql &> /dev/null; then
    echo "✓ PostgreSQL is installed"

    # Attempt to create database
    read -p "Create database now? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        python3 -c "
from db import Database
db = Database()
db.create_database()
db.connect()
db.init_schema()
db.close()
" && echo "✓ Database initialized" || echo "✗ Database initialization failed (check credentials in .env)"
    fi
else
    echo "⚠ PostgreSQL not found. Install with:"
    echo "  Ubuntu/Debian: sudo apt-get install postgresql postgresql-contrib"
    echo "  macOS: brew install postgresql"
    echo "  Or use: docker run -d -e POSTGRES_PASSWORD=password -p 5432:5432 postgres"
fi

echo
echo "=== Setup Complete ==="
echo
echo "Next steps:"
echo "1. Edit .env with your PostgreSQL credentials"
echo "2. Run: python main.py --mode collect --collect-data"
echo "3. Run: python main.py --mode simulate"
echo
