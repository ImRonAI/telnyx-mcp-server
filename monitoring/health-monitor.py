#!/usr/bin/env python3
"""
Comprehensive health monitoring for Telnyx MCP Server
Provides detailed health checks, metrics collection, and alerting
"""

import asyncio
import aiohttp
import json
import logging
import time
import os
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict
import sys

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@dataclass
class HealthMetrics:
    """Health metrics data structure"""
    timestamp: str
    status: str
    response_time_ms: float
    memory_usage_mb: Optional[float] = None
    cpu_usage_percent: Optional[float] = None
    active_connections: Optional[int] = None
    error_rate: Optional[float] = None
    uptime_seconds: Optional[float] = None

@dataclass
class HealthCheckResult:
    """Complete health check result"""
    overall_status: str
    metrics: HealthMetrics
    checks: Dict[str, Dict[str, Any]]
    issues: List[Dict[str, str]]
    recommendations: List[str]

class TelnyxMCPHealthMonitor:
    """Production-ready health monitor for Telnyx MCP Server"""
    
    def __init__(self, base_url: str = "http://localhost:8080"):
        self.base_url = base_url.rstrip('/')
        self.session: Optional[aiohttp.ClientSession] = None
        self.start_time = time.time()
        self.alert_thresholds = {
            'response_time_ms': 5000,  # 5 seconds
            'error_rate': 0.1,  # 10%
            'memory_usage_mb': 512,  # 512MB
            'cpu_usage_percent': 80,  # 80%
        }
        
    async def __aenter__(self):
        """Async context manager entry"""
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=10)
        )
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        if self.session:
            await self.session.close()
    
    async def check_basic_health(self) -> Dict[str, Any]:
        """Basic HTTP health check"""
        check_result = {
            'name': 'Basic Health Check',
            'status': 'unknown',
            'message': '',
            'response_time_ms': 0
        }
        
        try:
            start_time = time.time()
            
            # Try health endpoint first
            try:
                async with self.session.get(f"{self.base_url}/health") as response:
                    response_time = (time.time() - start_time) * 1000
                    check_result['response_time_ms'] = response_time
                    
                    if response.status == 200:
                        check_result['status'] = 'healthy'
                        check_result['message'] = 'Health endpoint responding normally'
                    else:
                        check_result['status'] = 'unhealthy'
                        check_result['message'] = f'Health endpoint returned status {response.status}'
                        
            except aiohttp.ClientConnectorError:
                # If health endpoint doesn't exist, try root endpoint
                async with self.session.get(f"{self.base_url}/") as response:
                    response_time = (time.time() - start_time) * 1000
                    check_result['response_time_ms'] = response_time
                    
                    if response.status in [200, 404]:  # 404 is acceptable for root
                        check_result['status'] = 'healthy'
                        check_result['message'] = 'Server responding (no health endpoint)'
                    else:
                        check_result['status'] = 'unhealthy'
                        check_result['message'] = f'Server returned status {response.status}'
                        
        except Exception as e:
            check_result['status'] = 'error'
            check_result['message'] = f'Health check failed: {str(e)}'
            
        return check_result
    
    async def check_mcp_capabilities(self) -> Dict[str, Any]:
        """Check MCP server capabilities"""
        check_result = {
            'name': 'MCP Capabilities Check',
            'status': 'unknown',
            'message': '',
            'tools_count': 0,
            'resources_count': 0,
            'prompts_count': 0
        }
        
        try:
            # Test MCP protocol endpoints (if available)
            endpoints_to_check = [
                '/mcp/tools',
                '/mcp/resources', 
                '/mcp/prompts',
                '/tools',
                '/resources',
                '/prompts'
            ]
            
            for endpoint in endpoints_to_check:
                try:
                    async with self.session.get(f"{self.base_url}{endpoint}") as response:
                        if response.status == 200:
                            data = await response.json()
                            if 'tools' in data:
                                check_result['tools_count'] = len(data.get('tools', []))
                            if 'resources' in data:
                                check_result['resources_count'] = len(data.get('resources', []))
                            if 'prompts' in data:
                                check_result['prompts_count'] = len(data.get('prompts', []))
                            break
                except Exception:
                    continue
                    
            if check_result['tools_count'] > 0:
                check_result['status'] = 'healthy'
                check_result['message'] = f"MCP server providing {check_result['tools_count']} tools"
            else:
                check_result['status'] = 'warning'
                check_result['message'] = 'No MCP tools detected'
                
        except Exception as e:
            check_result['status'] = 'error'
            check_result['message'] = f'MCP capabilities check failed: {str(e)}'
            
        return check_result
    
    async def check_authentication(self) -> Dict[str, Any]:
        """Check authentication configuration"""
        check_result = {
            'name': 'Authentication Check',
            'status': 'unknown',
            'message': ''
        }
        
        try:
            # Check if TELNYX_API_KEY is configured
            api_key = os.environ.get('TELNYX_API_KEY')
            
            if not api_key:
                check_result['status'] = 'error'
                check_result['message'] = 'TELNYX_API_KEY environment variable not set'
            elif not api_key.startswith('KEY'):
                check_result['status'] = 'error'
                check_result['message'] = 'TELNYX_API_KEY does not appear to be valid (should start with KEY)'
            elif len(api_key) < 20:
                check_result['status'] = 'warning'
                check_result['message'] = 'TELNYX_API_KEY appears to be too short'
            else:
                check_result['status'] = 'healthy'
                check_result['message'] = 'TELNYX_API_KEY is configured and appears valid'
                
        except Exception as e:
            check_result['status'] = 'error'
            check_result['message'] = f'Authentication check failed: {str(e)}'
            
        return check_result
    
    async def check_external_connectivity(self) -> Dict[str, Any]:
        """Check connectivity to Telnyx API"""
        check_result = {
            'name': 'External Connectivity Check',
            'status': 'unknown',
            'message': '',
            'api_reachable': False
        }
        
        try:
            # Test connectivity to Telnyx API
            async with self.session.get('https://api.telnyx.com/v2/') as response:
                if response.status in [200, 401, 403]:  # Any of these means API is reachable
                    check_result['api_reachable'] = True
                    check_result['status'] = 'healthy'
                    check_result['message'] = 'Telnyx API is reachable'
                else:
                    check_result['status'] = 'warning'
                    check_result['message'] = f'Telnyx API returned unexpected status {response.status}'
                    
        except Exception as e:
            check_result['status'] = 'error'
            check_result['message'] = f'Cannot reach Telnyx API: {str(e)}'
            
        return check_result
    
    def analyze_metrics(self, metrics: HealthMetrics) -> tuple[List[Dict], List[str]]:
        """Analyze metrics and generate issues/recommendations"""
        issues = []
        recommendations = []
        
        # Check response time
        if metrics.response_time_ms > self.alert_thresholds['response_time_ms']:
            issues.append({
                'type': 'performance',
                'severity': 'high',
                'message': f'High response time: {metrics.response_time_ms:.0f}ms'
            })
            recommendations.append('Consider optimizing server performance or increasing resources')
        
        # Check memory usage
        if metrics.memory_usage_mb and metrics.memory_usage_mb > self.alert_thresholds['memory_usage_mb']:
            issues.append({
                'type': 'resource',
                'severity': 'medium',
                'message': f'High memory usage: {metrics.memory_usage_mb:.0f}MB'
            })
            recommendations.append('Monitor memory usage and consider increasing memory limits')
        
        # Check error rate
        if metrics.error_rate and metrics.error_rate > self.alert_thresholds['error_rate']:
            issues.append({
                'type': 'reliability',
                'severity': 'high',
                'message': f'High error rate: {metrics.error_rate:.1%}'
            })
            recommendations.append('Investigate server logs for error patterns')
        
        return issues, recommendations
    
    async def perform_comprehensive_health_check(self) -> HealthCheckResult:
        """Perform comprehensive health check"""
        start_time = time.time()
        
        # Run all health checks
        checks = {}
        checks['basic_health'] = await self.check_basic_health()
        checks['mcp_capabilities'] = await self.check_mcp_capabilities()
        checks['authentication'] = await self.check_authentication()
        checks['external_connectivity'] = await self.check_external_connectivity()
        
        # Calculate overall response time
        total_response_time = (time.time() - start_time) * 1000
        
        # Create metrics
        metrics = HealthMetrics(
            timestamp=datetime.now().isoformat(),
            status='healthy',
            response_time_ms=total_response_time,
            uptime_seconds=time.time() - self.start_time
        )
        
        # Determine overall status
        statuses = [check['status'] for check in checks.values()]
        if 'error' in statuses:
            overall_status = 'unhealthy'
            metrics.status = 'unhealthy'
        elif 'warning' in statuses:
            overall_status = 'degraded'
            metrics.status = 'degraded'
        else:
            overall_status = 'healthy'
        
        # Analyze metrics for issues and recommendations
        issues, recommendations = self.analyze_metrics(metrics)
        
        return HealthCheckResult(
            overall_status=overall_status,
            metrics=metrics,
            checks=checks,
            issues=issues,
            recommendations=recommendations
        )
    
    async def continuous_monitoring(self, interval_seconds: int = 30, duration_seconds: Optional[int] = None):
        """Run continuous monitoring"""
        logger.info(f"Starting continuous monitoring (interval: {interval_seconds}s)")
        
        end_time = None
        if duration_seconds:
            end_time = time.time() + duration_seconds
        
        while True:
            try:
                result = await self.perform_comprehensive_health_check()
                
                # Log health status
                logger.info(f"Health Status: {result.overall_status} "
                           f"(Response Time: {result.metrics.response_time_ms:.0f}ms)")
                
                # Log any issues
                for issue in result.issues:
                    logger.warning(f"Issue ({issue['severity']}): {issue['message']}")
                
                # Log recommendations
                for rec in result.recommendations:
                    logger.info(f"Recommendation: {rec}")
                
                # Check if we should stop
                if end_time and time.time() >= end_time:
                    break
                    
                await asyncio.sleep(interval_seconds)
                
            except KeyboardInterrupt:
                logger.info("Monitoring stopped by user")
                break
            except Exception as e:
                logger.error(f"Monitoring error: {e}")
                await asyncio.sleep(interval_seconds)

async def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Telnyx MCP Server Health Monitor')
    parser.add_argument('--url', default='http://localhost:8080', 
                       help='MCP Server URL (default: http://localhost:8080)')
    parser.add_argument('--continuous', action='store_true',
                       help='Run continuous monitoring')
    parser.add_argument('--interval', type=int, default=30,
                       help='Monitoring interval in seconds (default: 30)')
    parser.add_argument('--duration', type=int, 
                       help='Duration to run monitoring in seconds')
    parser.add_argument('--json', action='store_true',
                       help='Output results in JSON format')
    
    args = parser.parse_args()
    
    async with TelnyxMCPHealthMonitor(args.url) as monitor:
        if args.continuous:
            await monitor.continuous_monitoring(args.interval, args.duration)
        else:
            result = await monitor.perform_comprehensive_health_check()
            
            if args.json:
                print(json.dumps(asdict(result), indent=2))
            else:
                print(f"\n=== Telnyx MCP Server Health Check ===")
                print(f"Overall Status: {result.overall_status}")
                print(f"Timestamp: {result.metrics.timestamp}")
                print(f"Response Time: {result.metrics.response_time_ms:.0f}ms")
                if result.metrics.uptime_seconds:
                    print(f"Uptime: {result.metrics.uptime_seconds:.0f}s")
                
                print("\n=== Check Results ===")
                for name, check in result.checks.items():
                    status_icon = "✅" if check['status'] == 'healthy' else "⚠️" if check['status'] == 'warning' else "❌"
                    print(f"{status_icon} {check['name']}: {check['status']} - {check['message']}")
                
                if result.issues:
                    print("\n=== Issues ===")
                    for issue in result.issues:
                        print(f"• {issue['message']} ({issue['severity']})")
                
                if result.recommendations:
                    print("\n=== Recommendations ===")
                    for rec in result.recommendations:
                        print(f"• {rec}")
                
                # Set exit code based on health status
                if result.overall_status == 'unhealthy':
                    sys.exit(1)
                elif result.overall_status == 'degraded':
                    sys.exit(2)

if __name__ == "__main__":
    asyncio.run(main())