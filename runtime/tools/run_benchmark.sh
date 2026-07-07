#!/bin/bash
# Daily Synthesus Benchmark Runner
# Runs at 8:00 AM CDT (America/Chicago)

cd /home/workspace/synthesus3.0

echo "=== Starting Daily Benchmark Run: $(date) ==="

# Run the benchmark suite
python3 benchmarks/benchmark_suite.py
BENCHMARK_EXIT=$?

# Get current date for file operations
DATE_STR=$(date +%Y-%m-%d)

# If benchmark ran successfully, commit and push
if [ $BENCHMARK_EXIT -eq 0 ]; then
    echo "=== Benchmark completed successfully ==="
    
    # Check if there are changes to commit
    cd /home/workspace/synthesus3.0
    git add benchmarks/
    
    if git diff --staged --quiet; then
        echo "No changes to commit"
    else
        git commit -m "Daily benchmark $DATE_STR"
        git push origin main || git push origin master
        echo "Changes committed and pushed"
    fi
    
    # Save full report to Zo Files
    cp "benchmarks/results/benchmark_${DATE_STR}.json" "/home/workspace/synthesus_benchmark_${DATE_STR}.json"
    echo "Full report saved to /home/workspace/synthesus_benchmark_${DATE_STR}.json"
else
    echo "Benchmark failed with exit code $BENCHMARK_EXIT"
fi

echo "=== Benchmark Run Complete: $(date) ==="
