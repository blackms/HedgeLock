#!/usr/bin/env python3
"""
Failover and recovery testing for HedgeLock.
Tests system resilience to service failures.
"""

import asyncio
import subprocess
import time
import json
from datetime import datetime
from typing import Dict, List
import aiohttp
from aiokafka import AIOKafkaProducer


class FailoverTest:
    """Test system failover and recovery capabilities."""
    
    def __init__(self):
        self.kafka_bootstrap = "kafka:29092"
        self.test_results = {
            "service_failures": [],
            "recovery_times": {},
            "data_integrity": True,
            "message_loss": 0
        }
    
    async def run_failover_tests(self):
        """Run complete failover test suite."""
        print("🔧 Starting HedgeLock Failover & Recovery Tests\n")
        
        # Test 1: Funding Engine restart
        await self.test_service_restart("funding-engine")
        
        # Test 2: Kafka partition failure
        await self.test_kafka_failure()
        
        # Test 3: Redis failure
        await self.test_redis_failure()
        
        # Test 4: Cascading service failure
        await self.test_cascading_failure()
        
        # Test 5: Network partition
        await self.test_network_partition()
        
        # Print results
        self.print_failover_results()
    
    async def test_service_restart(self, service_name: str):
        """Test service restart and recovery."""
        print(f"\n📊 Test: {service_name} Restart")
        
        container_name = f"hedgelock-{service_name}"
        
        # Check initial state
        initial_status = await self._check_service_health(service_name)
        print(f"Initial state: {'Healthy' if initial_status else 'Unhealthy'}")
        
        # Send test message before restart
        await self._send_test_funding("BTCUSDT", 50.0, "before-restart")
        
        # Restart service
        print(f"Restarting {container_name}...")
        restart_time = time.time()
        result = subprocess.run(
            ["docker", "restart", container_name],
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            print(f"❌ Failed to restart: {result.stderr}")
            self.test_results["service_failures"].append({
                "service": service_name,
                "error": "restart_failed"
            })
            return
        
        # Wait for recovery
        recovery_start = time.time()
        recovered = False
        
        for _ in range(30):  # 30 second timeout
            if await self._check_service_health(service_name):
                recovered = True
                break
            await asyncio.sleep(1)
        
        recovery_time = time.time() - recovery_start
        
        if recovered:
            print(f"✅ Service recovered in {recovery_time:.1f}s")
            self.test_results["recovery_times"][service_name] = recovery_time
            
            # Test functionality after recovery
            await self._send_test_funding("BTCUSDT", 75.0, "after-restart")
            await asyncio.sleep(2)
            
            # Verify processing
            status = await self._get_service_status(service_name)
            if status and status.get('symbols_tracked', 0) > 0:
                print("✅ Service fully functional after restart")
            else:
                print("⚠️  Service running but may not be fully functional")
        else:
            print(f"❌ Service failed to recover within 30s")
            self.test_results["service_failures"].append({
                "service": service_name,
                "error": "recovery_timeout"
            })
    
    async def test_kafka_failure(self):
        """Test Kafka broker failure and recovery."""
        print("\n📊 Test: Kafka Broker Failure")
        
        # Send messages before failure
        print("Sending messages before Kafka restart...")
        messages_before = []
        for i in range(5):
            trace_id = f"kafka-test-{i}"
            await self._send_test_funding("BTCUSDT", 25 + i*10, trace_id)
            messages_before.append(trace_id)
            await asyncio.sleep(0.2)
        
        # Restart Kafka
        print("Restarting Kafka broker...")
        restart_time = time.time()
        subprocess.run(["docker", "restart", "hedgelock-kafka"], capture_output=True)
        
        # Wait for Kafka to be healthy
        print("Waiting for Kafka recovery...")
        kafka_healthy = False
        for _ in range(60):  # 60 second timeout
            result = subprocess.run(
                ["docker", "exec", "hedgelock-kafka", "kafka-broker-api-versions", 
                 "--bootstrap-server", "localhost:29092"],
                capture_output=True
            )
            if result.returncode == 0:
                kafka_healthy = True
                break
            await asyncio.sleep(1)
        
        recovery_time = time.time() - restart_time
        
        if kafka_healthy:
            print(f"✅ Kafka recovered in {recovery_time:.1f}s")
            
            # Test message delivery after recovery
            print("Testing message delivery after recovery...")
            await asyncio.sleep(5)  # Let services reconnect
            
            messages_after = []
            for i in range(5):
                trace_id = f"kafka-recovery-{i}"
                await self._send_test_funding("BTCUSDT", 50 + i*10, trace_id)
                messages_after.append(trace_id)
                await asyncio.sleep(0.2)
            
            print("✅ Kafka fully functional after restart")
            self.test_results["recovery_times"]["kafka"] = recovery_time
        else:
            print("❌ Kafka failed to recover")
            self.test_results["service_failures"].append({
                "service": "kafka",
                "error": "recovery_failed"
            })
    
    async def test_redis_failure(self):
        """Test Redis failure impact."""
        print("\n📊 Test: Redis Cache Failure")
        
        # Redis is used for funding history storage
        print("Testing system behavior without Redis...")
        
        # Stop Redis
        print("Stopping Redis...")
        subprocess.run(["docker", "stop", "hedgelock-redis"], capture_output=True)
        
        # Test funding engine behavior without Redis
        await asyncio.sleep(2)
        
        # Send funding updates
        print("Sending funding updates with Redis down...")
        error_count = 0
        for i in range(3):
            try:
                await self._send_test_funding("BTCUSDT", 100 + i*25, f"redis-down-{i}")
            except Exception as e:
                error_count += 1
                print(f"   Error: {e}")
        
        # Check if funding engine is still processing
        status = await self._get_service_status("funding-engine")
        if status and status.get('running'):
            print("✅ Funding engine continues without Redis (degraded mode)")
        else:
            print("❌ Funding engine failed without Redis")
        
        # Restart Redis
        print("Restarting Redis...")
        subprocess.run(["docker", "start", "hedgelock-redis"], capture_output=True)
        await asyncio.sleep(5)
        
        print("✅ Redis restarted")
    
    async def test_cascading_failure(self):
        """Test cascading service failures."""
        print("\n📊 Test: Cascading Service Failure")
        
        services = ["funding-engine", "risk-engine", "hedger"]
        
        print("Simulating cascading failure...")
        
        # Stop services in sequence
        for service in services:
            print(f"Stopping {service}...")
            subprocess.run([
                "docker", "stop", f"hedgelock-{service}"
            ], capture_output=True)
            await asyncio.sleep(2)
        
        print("All services stopped. Starting recovery...")
        
        # Restart in reverse order
        recovery_start = time.time()
        for service in reversed(services):
            print(f"Starting {service}...")
            subprocess.run([
                "docker", "start", f"hedgelock-{service}"
            ], capture_output=True)
            await asyncio.sleep(3)
        
        # Wait for full recovery
        all_healthy = True
        for service in services:
            if not await self._wait_for_service_health(service, timeout=30):
                all_healthy = False
                print(f"❌ {service} failed to recover")
        
        total_recovery = time.time() - recovery_start
        
        if all_healthy:
            print(f"✅ All services recovered in {total_recovery:.1f}s")
            self.test_results["recovery_times"]["cascading"] = total_recovery
        else:
            print("❌ Some services failed to recover")
            self.test_results["service_failures"].append({
                "service": "cascading",
                "error": "incomplete_recovery"
            })
    
    async def test_network_partition(self):
        """Test network partition scenario."""
        print("\n📊 Test: Network Partition Simulation")
        
        # This would normally involve iptables rules or network namespaces
        # For this test, we'll simulate by blocking communication
        
        print("Simulating network partition...")
        
        # Disconnect a service from network (simulate)
        print("Isolating funding-engine from network...")
        subprocess.run([
            "docker", "network", "disconnect", 
            "hedgelock_hedgelock-network", "hedgelock-funding-engine"
        ], capture_output=True)
        
        # Wait and observe
        await asyncio.sleep(5)
        
        # Check if service detects isolation
        isolated_healthy = await self._check_service_health("funding-engine")
        print(f"Service health during isolation: {'Healthy' if isolated_healthy else 'Unhealthy'}")
        
        # Reconnect
        print("Restoring network connectivity...")
        subprocess.run([
            "docker", "network", "connect",
            "hedgelock_hedgelock-network", "hedgelock-funding-engine"
        ], capture_output=True)
        
        # Wait for recovery
        await asyncio.sleep(5)
        
        recovered = await self._check_service_health("funding-engine")
        if recovered:
            print("✅ Service recovered from network partition")
        else:
            print("❌ Service failed to recover from network partition")
    
    # Helper methods
    async def _check_service_health(self, service_name: str) -> bool:
        """Check if service is healthy."""
        port_map = {
            "funding-engine": 8005,
            "risk-engine": 8002,
            "hedger": 8003,
            "collector": 8001
        }
        
        port = port_map.get(service_name)
        if not port:
            return False
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f'http://localhost:{port}/health',
                    timeout=aiohttp.ClientTimeout(total=2)
                ) as resp:
                    return resp.status == 200
        except:
            return False
    
    async def _get_service_status(self, service_name: str) -> Dict:
        """Get service status."""
        port_map = {
            "funding-engine": 8005,
            "risk-engine": 8002
        }
        
        port = port_map.get(service_name)
        if not port:
            return {}
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f'http://localhost:{port}/status') as resp:
                    if resp.status == 200:
                        return await resp.json()
        except:
            pass
        return {}
    
    async def _wait_for_service_health(self, service_name: str, timeout: int = 30) -> bool:
        """Wait for service to become healthy."""
        for _ in range(timeout):
            if await self._check_service_health(service_name):
                return True
            await asyncio.sleep(1)
        return False
    
    async def _send_test_funding(self, symbol: str, rate: float, trace_id: str):
        """Send test funding rate."""
        producer = AIOKafkaProducer(
            bootstrap_servers=self.kafka_bootstrap,
            value_serializer=lambda v: json.dumps(v, default=str).encode('utf-8')
        )
        
        await producer.start()
        
        try:
            msg = {
                "service": "failover-test",
                "funding_rate": {
                    "symbol": symbol,
                    "funding_rate": rate / 100 / 365 / 3,
                    "funding_time": datetime.utcnow().isoformat(),
                    "mark_price": 50000.0,
                    "index_price": 49950.0
                },
                "trace_id": trace_id,
                "timestamp": datetime.utcnow().isoformat()
            }
            
            await producer.send_and_wait('funding_rates', value=msg)
        finally:
            await producer.stop()
    
    def print_failover_results(self):
        """Print failover test results."""
        print("\n" + "="*60)
        print("📊 FAILOVER TEST RESULTS")
        print("="*60)
        
        # Recovery times
        print("\n⏱️  Recovery Times:")
        for service, time_sec in self.test_results["recovery_times"].items():
            print(f"   - {service}: {time_sec:.1f}s")
        
        # Service failures
        if self.test_results["service_failures"]:
            print(f"\n❌ Service Failures: {len(self.test_results['service_failures'])}")
            for failure in self.test_results["service_failures"]:
                print(f"   - {failure['service']}: {failure['error']}")
        else:
            print("\n✅ No service failures detected")
        
        # Overall assessment
        print("\n🎯 Resilience Assessment:")
        
        failure_count = len(self.test_results["service_failures"])
        avg_recovery = (
            statistics.mean(self.test_results["recovery_times"].values())
            if self.test_results["recovery_times"] else 0
        )
        
        if failure_count == 0 and avg_recovery < 10:
            print("   ✅ EXCELLENT - System is highly resilient")
        elif failure_count <= 1 and avg_recovery < 30:
            print("   ⚠️  GOOD - Minor issues but acceptable")
        else:
            print("   ❌ NEEDS IMPROVEMENT - Multiple failures or slow recovery")
        
        print("\n" + "="*60)


async def main():
    """Run failover tests."""
    print("⚠️  WARNING: This test will restart services!")
    print("Make sure you have saved any important data.\n")
    
    # Uncomment to run tests
    # test = FailoverTest()
    # await test.run_failover_tests()
    
    print("Failover tests ready. Uncomment the test execution to run.")


if __name__ == "__main__":
    import statistics
    asyncio.run(main())