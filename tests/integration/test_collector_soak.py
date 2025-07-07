"""
Collector soak test - tests WebSocket reconnection and data gap handling.
"""

import asyncio
import time
import sys
from datetime import datetime, timedelta
from typing import List, Dict, Any
import json
from aiokafka import AIOKafkaConsumer
from unittest.mock import patch, AsyncMock

from src.hedgelock.config import settings
from src.hedgelock.collector.websocket_client import WebSocketManager
from src.hedgelock.collector.kafka_producer import KafkaProducerWrapper
from src.hedgelock.logging import get_logger

logger = get_logger(__name__)


class CollectorSoakTest:
    """Soak test for collector service resilience."""
    
    def __init__(self):
        self.messages_received: List[Dict[str, Any]] = []
        self.gaps_detected: List[Dict[str, Any]] = []
        self.last_message_time: Dict[str, datetime] = {}
        self.max_allowed_gap_seconds = 15
        self.test_duration_seconds = 300  # 5 minutes
        self.ws_kill_interval_seconds = 60  # Kill WS every minute
        self.consumer: AIOKafkaConsumer = None
        
    async def setup(self):
        """Set up test consumer."""
        self.consumer = AIOKafkaConsumer(
            settings.kafka.topic_account_raw,
            bootstrap_servers=settings.kafka.bootstrap_servers,
            group_id="collector_soak_test",
            value_deserializer=lambda m: json.loads(m.decode('utf-8')),
            auto_offset_reset='latest'
        )
        await self.consumer.start()
        logger.info("Soak test consumer started")
        
    async def teardown(self):
        """Clean up resources."""
        if self.consumer:
            await self.consumer.stop()
            
    async def consume_messages(self):
        """Consume messages and check for gaps."""
        async for message in self.consumer:
            msg_data = message.value
            source = msg_data.get("source", "unknown")
            timestamp = datetime.fromisoformat(msg_data["timestamp"])
            
            self.messages_received.append({
                "timestamp": timestamp,
                "source": source,
                "offset": message.offset
            })
            
            # Check for data gaps
            if source in self.last_message_time:
                gap_seconds = (timestamp - self.last_message_time[source]).total_seconds()
                if gap_seconds > self.max_allowed_gap_seconds:
                    gap_info = {
                        "source": source,
                        "gap_seconds": gap_seconds,
                        "last_seen": self.last_message_time[source],
                        "current": timestamp
                    }
                    self.gaps_detected.append(gap_info)
                    logger.warning(f"Data gap detected: {gap_info}")
            
            self.last_message_time[source] = timestamp
            
    async def simulate_ws_failures(self, ws_manager: WebSocketManager):
        """Simulate WebSocket connection failures."""
        kill_count = 0
        
        while kill_count < self.test_duration_seconds / self.ws_kill_interval_seconds:
            await asyncio.sleep(self.ws_kill_interval_seconds)
            
            logger.info(f"Simulating WebSocket failure #{kill_count + 1}")
            
            # Force close WebSocket connections
            if ws_manager.public_ws:
                await ws_manager.public_ws.close()
            if ws_manager.private_ws:
                await ws_manager.private_ws.close()
            
            kill_count += 1
            
            # Wait for reconnection
            await asyncio.sleep(5)
            
    def analyze_results(self) -> Dict[str, Any]:
        """Analyze test results."""
        total_messages = len(self.messages_received)
        total_gaps = len(self.gaps_detected)
        
        # Calculate message rate
        if self.messages_received:
            first_msg_time = self.messages_received[0]["timestamp"]
            last_msg_time = self.messages_received[-1]["timestamp"]
            duration = (last_msg_time - first_msg_time).total_seconds()
            message_rate = total_messages / duration if duration > 0 else 0
        else:
            message_rate = 0
            
        # Find longest gap
        longest_gap = max(self.gaps_detected, key=lambda x: x["gap_seconds"]) if self.gaps_detected else None
        
        return {
            "total_messages": total_messages,
            "total_gaps": total_gaps,
            "message_rate_per_second": round(message_rate, 2),
            "gaps_over_15s": [g for g in self.gaps_detected if g["gap_seconds"] > 15],
            "longest_gap": longest_gap,
            "test_passed": all(g["gap_seconds"] <= self.max_allowed_gap_seconds for g in self.gaps_detected)
        }


async def run_soak_test():
    """Run the collector soak test."""
    test = CollectorSoakTest()
    
    try:
        await test.setup()
        
        # Create mock WebSocket manager for testing
        ws_manager = WebSocketManager(
            kafka_producer=AsyncMock(),
            api_key="test_key",
            api_secret="test_secret"
        )
        
        # Start consuming messages
        consume_task = asyncio.create_task(test.consume_messages())
        
        # Start WebSocket failure simulation
        failure_task = asyncio.create_task(test.simulate_ws_failures(ws_manager))
        
        # Run test for specified duration
        logger.info(f"Running soak test for {test.test_duration_seconds} seconds...")
        await asyncio.sleep(test.test_duration_seconds)
        
        # Cancel tasks
        consume_task.cancel()
        failure_task.cancel()
        
        # Analyze results
        results = test.analyze_results()
        
        # Print results
        print("\n" + "="*50)
        print("COLLECTOR SOAK TEST RESULTS")
        print("="*50)
        print(f"Total messages received: {results['total_messages']}")
        print(f"Message rate: {results['message_rate_per_second']} msg/s")
        print(f"Total gaps detected: {results['total_gaps']}")
        print(f"Gaps over 15s: {len(results['gaps_over_15s'])}")
        
        if results['longest_gap']:
            print(f"Longest gap: {results['longest_gap']['gap_seconds']:.1f}s")
            
        print(f"\nTest result: {'PASSED' if results['test_passed'] else 'FAILED'}")
        print("="*50)
        
        # Exit with appropriate code
        sys.exit(0 if results['test_passed'] else 1)
        
    except Exception as e:
        logger.error(f"Soak test failed with error: {e}")
        sys.exit(2)
    finally:
        await test.teardown()


def main():
    """Main entry point for soak test script."""
    # Check if Kafka is running
    try:
        import subprocess
        result = subprocess.run(
            ["docker", "ps", "--filter", "name=kafka", "--format", "{{.Names}}"],
            capture_output=True,
            text=True
        )
        if "kafka" not in result.stdout:
            print("ERROR: Kafka container is not running. Start docker-compose first.")
            sys.exit(1)
    except Exception:
        print("WARNING: Could not check if Kafka is running")
    
    # Run the soak test
    asyncio.run(run_soak_test())


if __name__ == "__main__":
    main()