#!/usr/bin/env python3
"""
Real-time funding regime monitoring dashboard.
Displays current funding rates, regimes, and position adjustments.
"""

import asyncio
import json
import os
import sys
from datetime import datetime
from typing import Dict, Optional
import aiohttp
from rich.console import Console
from rich.table import Table
from rich.live import Live
from rich.panel import Panel
from rich.layout import Layout
from rich.text import Text
from aiokafka import AIOKafkaConsumer


class FundingMonitor:
    """Real-time funding monitoring dashboard."""
    
    def __init__(self):
        self.console = Console()
        self.kafka_bootstrap = "localhost:9092"
        self.funding_contexts: Dict[str, dict] = {}
        self.funding_rates: Dict[str, dict] = {}
        self.stats = {
            "messages_received": 0,
            "regime_changes": 0,
            "emergency_exits": 0,
            "last_update": None
        }
        
    def create_layout(self) -> Layout:
        """Create dashboard layout."""
        layout = Layout()
        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="main", ratio=1),
            Layout(name="footer", size=3)
        )
        
        layout["main"].split_row(
            Layout(name="funding_table"),
            Layout(name="stats", ratio=1)
        )
        
        return layout
    
    def generate_header(self) -> Panel:
        """Generate header panel."""
        return Panel(
            Text("🚀 HedgeLock Funding Awareness Monitor", justify="center", style="bold blue"),
            title="v1.2.0",
            border_style="blue"
        )
    
    def generate_footer(self) -> Panel:
        """Generate footer panel."""
        footer_text = f"Last Update: {self.stats['last_update'] or 'Never'} | Messages: {self.stats['messages_received']} | Press Ctrl+C to exit"
        return Panel(Text(footer_text, justify="center"), border_style="dim")
    
    def generate_funding_table(self) -> Panel:
        """Generate funding rates table."""
        table = Table(title="Funding Rates & Regimes")
        
        table.add_column("Symbol", style="cyan", width=12)
        table.add_column("Rate (APR)", justify="right", style="yellow")
        table.add_column("Regime", justify="center", width=10)
        table.add_column("Position\nMultiplier", justify="right", style="green")
        table.add_column("Action", width=20)
        table.add_column("Daily Cost", justify="right", style="magenta")
        
        # Color mapping for regimes
        regime_colors = {
            "neutral": "green",
            "normal": "blue", 
            "heated": "yellow",
            "mania": "red",
            "extreme": "bold red on white"
        }
        
        for symbol, context in sorted(self.funding_contexts.items()):
            fc = context.get("funding_context", {})
            fd = context.get("funding_decision", {})
            
            rate = fc.get("current_rate", 0)
            regime = fc.get("current_regime", "unknown")
            multiplier = fc.get("position_multiplier", 1.0)
            should_exit = fc.get("should_exit", False)
            action = fd.get("action", "none")
            daily_cost = fc.get("daily_cost_bps", 0)
            
            # Format rate with color based on level
            if rate > 300:
                rate_str = f"[bold red]{rate:.1f}%[/bold red]"
            elif rate > 100:
                rate_str = f"[red]{rate:.1f}%[/red]"
            elif rate > 50:
                rate_str = f"[yellow]{rate:.1f}%[/yellow]"
            else:
                rate_str = f"[green]{rate:.1f}%[/green]"
            
            # Format regime with color
            regime_color = regime_colors.get(regime, "white")
            regime_str = f"[{regime_color}]{regime.upper()}[/{regime_color}]"
            
            # Format multiplier
            if multiplier == 0:
                mult_str = "[bold red]0.00[/bold red]"
            elif multiplier < 0.5:
                mult_str = f"[yellow]{multiplier:.2f}[/yellow]"
            else:
                mult_str = f"[green]{multiplier:.2f}[/green]"
            
            # Format action
            if should_exit:
                action_str = "[bold red]⚠️  EMERGENCY EXIT[/bold red]"
            elif action == "reduce_position":
                action_str = "[yellow]📉 Reduce Position[/yellow]"
            elif action == "increase_position":
                action_str = "[green]📈 Increase Position[/green]"
            else:
                action_str = "[blue]✓ Maintain[/blue]"
            
            # Format daily cost
            cost_str = f"{daily_cost:.1f} bps"
            
            table.add_row(
                symbol,
                rate_str,
                regime_str,
                mult_str,
                action_str,
                cost_str
            )
        
        if not self.funding_contexts:
            table.add_row("No data", "-", "-", "-", "-", "-")
        
        return Panel(table, title="Real-Time Funding Status", border_style="green")
    
    def generate_stats_panel(self) -> Panel:
        """Generate statistics panel."""
        stats_text = f"""
📊 System Statistics

Messages Received: {self.stats['messages_received']}
Regime Changes: {self.stats['regime_changes']}
Emergency Exits: {self.stats['emergency_exits']}

🎯 Current Status:
Active Symbols: {len(self.funding_contexts)}
Extreme Regimes: {sum(1 for c in self.funding_contexts.values() if c.get('funding_context', {}).get('current_regime') == 'extreme')}
Reduced Positions: {sum(1 for c in self.funding_contexts.values() if c.get('funding_context', {}).get('position_multiplier', 1) < 1.0)}

⚙️  Services:
Funding Engine: http://localhost:8005/status
Risk Engine: http://localhost:8002/status
Kafka UI: http://localhost:8080
        """
        
        # Add alerts section if there are any extreme regimes
        extreme_symbols = [s for s, c in self.funding_contexts.items() 
                          if c.get('funding_context', {}).get('should_exit', False)]
        
        if extreme_symbols:
            stats_text += f"\n\n🚨 ALERTS:\n"
            for symbol in extreme_symbols:
                stats_text += f"  - {symbol}: EXTREME FUNDING - EXIT ALL POSITIONS\n"
        
        return Panel(stats_text, title="Dashboard Stats", border_style="blue")
    
    async def consume_funding_contexts(self):
        """Consume funding context messages from Kafka."""
        consumer = AIOKafkaConsumer(
            'funding_context',
            bootstrap_servers=self.kafka_bootstrap,
            auto_offset_reset='latest',
            value_deserializer=lambda m: json.loads(m.decode('utf-8'))
        )
        
        await consumer.start()
        
        try:
            async for msg in consumer:
                self.stats['messages_received'] += 1
                self.stats['last_update'] = datetime.now().strftime("%H:%M:%S")
                
                # Extract funding context
                symbol = msg.value.get('funding_context', {}).get('symbol')
                if symbol:
                    # Check for regime change
                    old_regime = self.funding_contexts.get(symbol, {}).get('funding_context', {}).get('current_regime')
                    new_regime = msg.value.get('funding_context', {}).get('current_regime')
                    
                    if old_regime and old_regime != new_regime:
                        self.stats['regime_changes'] += 1
                    
                    # Check for emergency exit
                    if msg.value.get('funding_context', {}).get('should_exit', False):
                        self.stats['emergency_exits'] += 1
                    
                    # Store context
                    self.funding_contexts[symbol] = msg.value
                    
        except Exception as e:
            self.console.print(f"[red]Error consuming messages: {e}[/red]")
        finally:
            await consumer.stop()
    
    async def check_service_health(self):
        """Periodically check service health."""
        while True:
            try:
                async with aiohttp.ClientSession() as session:
                    # Check funding engine
                    async with session.get('http://localhost:8005/status') as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            # Update contexts from API if available
                            contexts = data.get('contexts', {})
                            for symbol, ctx in contexts.items():
                                if symbol not in self.funding_contexts:
                                    # Create a minimal context from status
                                    self.funding_contexts[symbol] = {
                                        'funding_context': {
                                            'symbol': symbol,
                                            'current_regime': ctx.get('regime', 'unknown'),
                                            'current_rate': float(ctx.get('current_rate', '0').rstrip('%')),
                                            'position_multiplier': ctx.get('multiplier', 1.0),
                                            'should_exit': ctx.get('should_exit', False),
                                            'daily_cost_bps': 0
                                        },
                                        'funding_decision': {
                                            'action': 'monitor'
                                        }
                                    }
                            
            except Exception:
                pass  # Ignore errors in health check
            
            await asyncio.sleep(5)
    
    async def run(self):
        """Run the monitoring dashboard."""
        layout = self.create_layout()
        
        # Start background tasks
        consumer_task = asyncio.create_task(self.consume_funding_contexts())
        health_task = asyncio.create_task(self.check_service_health())
        
        try:
            with Live(layout, refresh_per_second=1, screen=True) as live:
                while True:
                    layout["header"].update(self.generate_header())
                    layout["main"]["funding_table"].update(self.generate_funding_table())
                    layout["main"]["stats"].update(self.generate_stats_panel())
                    layout["footer"].update(self.generate_footer())
                    
                    await asyncio.sleep(1)
                    
        except KeyboardInterrupt:
            self.console.print("\n[yellow]Shutting down monitor...[/yellow]")
        finally:
            consumer_task.cancel()
            health_task.cancel()
            await asyncio.gather(consumer_task, health_task, return_exceptions=True)


async def main():
    """Run the funding monitor."""
    monitor = FundingMonitor()
    await monitor.run()


if __name__ == "__main__":
    # Check if rich is installed
    try:
        import rich
    except ImportError:
        print("Error: 'rich' library is required for the monitoring dashboard")
        print("Install it with: pip install rich")
        sys.exit(1)
    
    print("Starting HedgeLock Funding Monitor...")
    print("Connecting to Kafka at localhost:9092...")
    print("\nNote: Make sure to send some funding rate messages to see data!")
    print("Press Ctrl+C to exit\n")
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nMonitor stopped.")