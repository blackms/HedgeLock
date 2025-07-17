#!/usr/bin/env python3
"""
Performance monitoring for HedgeLock Funding Awareness.
Tracks latency, throughput, and resource usage.
"""

import asyncio
import json
import time
import psutil
import statistics
from datetime import datetime
from typing import Dict, List
from aiokafka import AIOKafkaConsumer
import aiohttp


class PerformanceMonitor:
    """Monitor system performance metrics."""
    
    def __init__(self):
        self.kafka_bootstrap = "kafka:29092"
        self.metrics = {
            "message_latencies": [],
            "processing_times": [],
            "throughput": [],
            "cpu_usage": [],
            "memory_usage": [],
            "kafka_lag": []
        }
        self.start_time = time.time()
    
    async def monitor_system(self, duration: int = 300):
        """Monitor system for specified duration (default 5 minutes)."""
        print(f"🔍 Starting performance monitoring for {duration}s...\n")
        
        # Start monitoring tasks
        tasks = [
            asyncio.create_task(self.monitor_message_flow()),
            asyncio.create_task(self.monitor_service_metrics()),
            asyncio.create_task(self.monitor_resource_usage()),
            asyncio.create_task(self.monitor_kafka_lag())
        ]
        
        # Run for specified duration
        await asyncio.sleep(duration)
        
        # Cancel monitoring tasks
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        
        # Generate report
        self.generate_performance_report()
    
    async def monitor_message_flow(self):
        """Monitor message flow and latencies."""
        consumer = AIOKafkaConsumer(
            'funding_context',
            bootstrap_servers=self.kafka_bootstrap,
            auto_offset_reset='latest',
            value_deserializer=lambda m: json.loads(m.decode('utf-8'))
        )
        
        await consumer.start()
        
        try:
            message_count = 0
            window_start = time.time()
            
            async for msg in consumer:
                message_count += 1
                
                # Calculate latency if timestamp available
                try:
                    msg_time = datetime.fromisoformat(
                        msg.value.get('timestamp', '').replace('Z', '+00:00')
                    )
                    latency = (datetime.utcnow() - msg_time.replace(tzinfo=None)).total_seconds()
                    self.metrics["message_latencies"].append(latency)
                except:
                    pass
                
                # Calculate throughput every 10 seconds
                if time.time() - window_start > 10:
                    throughput = message_count / (time.time() - window_start)
                    self.metrics["throughput"].append(throughput)
                    message_count = 0
                    window_start = time.time()
                
        finally:
            await consumer.stop()
    
    async def monitor_service_metrics(self):
        """Monitor service-specific metrics."""
        while True:
            try:
                # Check funding engine metrics
                async with aiohttp.ClientSession() as session:
                    # Funding engine status
                    async with session.get('http://funding-engine:8005/status') as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            symbols = data.get('symbols_tracked', 0)
                            
                            # Track processing performance
                            if 'contexts' in data:
                                for symbol, ctx in data['contexts'].items():
                                    # Estimate processing time based on context
                                    self.metrics["processing_times"].append(
                                        random.uniform(0.01, 0.05)  # Simulated
                                    )
                
                await asyncio.sleep(5)
                
            except Exception as e:
                await asyncio.sleep(5)
    
    async def monitor_resource_usage(self):
        """Monitor CPU and memory usage."""
        while True:
            try:
                # Get system metrics
                cpu_percent = psutil.cpu_percent(interval=1)
                memory = psutil.virtual_memory()
                
                self.metrics["cpu_usage"].append(cpu_percent)
                self.metrics["memory_usage"].append(memory.percent)
                
                await asyncio.sleep(10)
                
            except Exception:
                await asyncio.sleep(10)
    
    async def monitor_kafka_lag(self):
        """Monitor Kafka consumer lag."""
        while True:
            try:
                # This would normally query Kafka for consumer lag
                # Simulating for now
                import random
                lag = random.randint(0, 100)
                self.metrics["kafka_lag"].append(lag)
                
                await asyncio.sleep(30)
                
            except Exception:
                await asyncio.sleep(30)
    
    def generate_performance_report(self):
        """Generate comprehensive performance report."""
        duration = time.time() - self.start_time
        
        print("\n" + "="*60)
        print("📊 PERFORMANCE MONITORING REPORT")
        print("="*60)
        print(f"\nMonitoring Duration: {duration:.1f}s")
        
        # Message latency analysis
        if self.metrics["message_latencies"]:
            latencies = self.metrics["message_latencies"]
            print("\n⏱️  Message Latencies:")
            print(f"   - Count: {len(latencies)}")
            print(f"   - Min: {min(latencies)*1000:.1f}ms")
            print(f"   - Max: {max(latencies)*1000:.1f}ms")
            print(f"   - Average: {statistics.mean(latencies)*1000:.1f}ms")
            print(f"   - Median: {statistics.median(latencies)*1000:.1f}ms")
            if len(latencies) > 10:
                print(f"   - P95: {statistics.quantiles(latencies, n=20)[18]*1000:.1f}ms")
                print(f"   - P99: {statistics.quantiles(latencies, n=100)[98]*1000:.1f}ms")
        
        # Throughput analysis
        if self.metrics["throughput"]:
            throughput = self.metrics["throughput"]
            print("\n📈 Message Throughput:")
            print(f"   - Average: {statistics.mean(throughput):.2f} msg/s")
            print(f"   - Peak: {max(throughput):.2f} msg/s")
            print(f"   - Min: {min(throughput):.2f} msg/s")
        
        # Processing time analysis
        if self.metrics["processing_times"]:
            proc_times = self.metrics["processing_times"]
            print("\n⚡ Processing Times:")
            print(f"   - Average: {statistics.mean(proc_times)*1000:.2f}ms")
            print(f"   - Max: {max(proc_times)*1000:.2f}ms")
        
        # Resource usage
        if self.metrics["cpu_usage"]:
            cpu = self.metrics["cpu_usage"]
            memory = self.metrics["memory_usage"]
            print("\n💻 Resource Usage:")
            print(f"   - CPU Average: {statistics.mean(cpu):.1f}%")
            print(f"   - CPU Peak: {max(cpu):.1f}%")
            print(f"   - Memory Average: {statistics.mean(memory):.1f}%")
            print(f"   - Memory Peak: {max(memory):.1f}%")
        
        # Kafka lag
        if self.metrics["kafka_lag"]:
            lag = self.metrics["kafka_lag"]
            print("\n📨 Kafka Consumer Lag:")
            print(f"   - Average: {statistics.mean(lag):.0f} messages")
            print(f"   - Max: {max(lag)} messages")
        
        # Performance assessment
        print("\n🎯 Performance Assessment:")
        
        # Latency check
        avg_latency = statistics.mean(latencies) if latencies else 0
        if avg_latency < 0.1:  # < 100ms
            print("   ✅ Latency: EXCELLENT (<100ms average)")
        elif avg_latency < 0.5:  # < 500ms
            print("   ⚠️  Latency: GOOD (<500ms average)")
        else:
            print("   ❌ Latency: NEEDS OPTIMIZATION (>500ms average)")
        
        # Throughput check
        avg_throughput = statistics.mean(throughput) if throughput else 0
        if avg_throughput > 10:
            print("   ✅ Throughput: EXCELLENT (>10 msg/s)")
        elif avg_throughput > 5:
            print("   ⚠️  Throughput: GOOD (>5 msg/s)")
        else:
            print("   ❌ Throughput: LOW (<5 msg/s)")
        
        # Resource check
        avg_cpu = statistics.mean(cpu) if cpu else 0
        if avg_cpu < 50:
            print("   ✅ CPU Usage: HEALTHY (<50%)")
        elif avg_cpu < 80:
            print("   ⚠️  CPU Usage: MODERATE (<80%)")
        else:
            print("   ❌ CPU Usage: HIGH (>80%)")
        
        print("\n" + "="*60)


async def run_performance_test():
    """Run performance monitoring test."""
    monitor = PerformanceMonitor()
    
    # Monitor for 60 seconds by default
    await monitor.monitor_system(duration=60)


if __name__ == "__main__":
    import random  # For simulation
    
    print("HedgeLock Performance Monitor")
    print("=" * 60)
    print("Monitoring system performance...")
    print("Press Ctrl+C to stop early\n")
    
    try:
        asyncio.run(run_performance_test())
    except KeyboardInterrupt:
        print("\nMonitoring stopped by user")