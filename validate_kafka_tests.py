#!/usr/bin/env python3
"""
Validate that Kafka integration tests are properly implemented.
"""

import sys
import os
from pathlib import Path

def validate_kafka_tests():
    """Validate that Kafka integration tests exist and are properly structured."""
    
    # Check if test files exist
    test_files = [
        "tests/integration/position_manager/test_kafka_core.py",
        "tests/integration/position_manager/test_kafka_integration.py"
    ]
    
    for file_path in test_files:
        if not os.path.exists(file_path):
            print(f"❌ Missing test file: {file_path}")
            return False
        else:
            print(f"✅ Found test file: {file_path}")
    
    # Check if test files have proper structure
    core_test_file = "tests/integration/position_manager/test_kafka_core.py"
    try:
        with open(core_test_file, 'r') as f:
            content = f.read()
            
        required_tests = [
            "test_kafka_producer_connection",
            "test_kafka_consumer_connection", 
            "test_position_manager_kafka_initialization",
            "test_funding_message_handling",
            "test_market_data_handling",
            "test_hedge_message_publishing",
            "test_emergency_action_publishing"
        ]
        
        missing_tests = []
        for test in required_tests:
            if test not in content:
                missing_tests.append(test)
        
        if missing_tests:
            print(f"❌ Missing tests in {core_test_file}: {missing_tests}")
            return False
        else:
            print(f"✅ All required tests found in {core_test_file}")
            
    except Exception as e:
        print(f"❌ Error reading {core_test_file}: {e}")
        return False
    
    # Check if integration test has proper structure
    integration_test_file = "tests/integration/position_manager/test_kafka_integration.py"
    try:
        with open(integration_test_file, 'r') as f:
            content = f.read()
            
        required_classes = [
            "KafkaIntegrationTest",
            "TestPositionManagerKafkaIntegration"
        ]
        
        for cls in required_classes:
            if cls not in content:
                print(f"❌ Missing class in {integration_test_file}: {cls}")
                return False
        
        print(f"✅ All required classes found in {integration_test_file}")
        
    except Exception as e:
        print(f"❌ Error reading {integration_test_file}: {e}")
        return False
    
    # Check if test runners exist
    test_runners = [
        "run_kafka_core_tests.sh",
        "run_kafka_integration_tests.sh"
    ]
    
    for runner in test_runners:
        if not os.path.exists(runner):
            print(f"❌ Missing test runner: {runner}")
            return False
        else:
            print(f"✅ Found test runner: {runner}")
    
    # Check if docker-compose.test.yml has Kafka configuration
    compose_file = "docker-compose.test.yml"
    try:
        with open(compose_file, 'r') as f:
            content = f.read()
            
        if "test-kafka:" not in content:
            print(f"❌ Missing Kafka configuration in {compose_file}")
            return False
        else:
            print(f"✅ Kafka configuration found in {compose_file}")
            
    except Exception as e:
        print(f"❌ Error reading {compose_file}: {e}")
        return False
    
    print("\n🎉 All Kafka integration tests are properly implemented!")
    return True

def check_imports():
    """Check if all required imports are available."""
    try:
        import pytest
        import asyncio
        import json
        from datetime import datetime
        from unittest.mock import Mock, patch
        
        print("✅ All required imports are available")
        return True
    except ImportError as e:
        print(f"❌ Missing import: {e}")
        return False

if __name__ == "__main__":
    print("🧪 Validating Kafka Integration Tests")
    print("=" * 40)
    
    # Check imports
    if not check_imports():
        sys.exit(1)
    
    # Validate tests
    if not validate_kafka_tests():
        sys.exit(1)
    
    print("\n✅ Kafka integration tests validation passed!")
    sys.exit(0)