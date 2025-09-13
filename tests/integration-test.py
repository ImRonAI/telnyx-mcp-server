#!/usr/bin/env python3
"""
Integration tests for Telnyx MCP Server
Tests the complete functionality of the deployed MCP server
"""

import asyncio
import aiohttp
import json
import logging
import os
import time
import subprocess
import signal
from datetime import datetime
from typing import Dict, List, Any, Optional
from pathlib import Path
import docker
from dataclasses import dataclass

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

@dataclass
class TestResult:
    """Test result data structure"""
    test_name: str
    status: str  # pass, fail, skip
    message: str
    duration_seconds: float
    details: Optional[Dict[str, Any]] = None

class TelnyxMCPIntegrationTest:
    """Integration test suite for Telnyx MCP Server"""
    
    def __init__(self, server_url: str = "http://localhost:8080", project_path: str = "."):
        self.server_url = server_url.rstrip('/')
        self.project_path = Path(project_path).resolve()
        self.results: List[TestResult] = []
        self.server_process = None
        self.docker_container = None
        self.docker_client = None
        
        # Initialize Docker client
        try:
            self.docker_client = docker.from_env()
        except Exception as e:
            logger.warning(f"Docker client initialization failed: {e}")
    
    async def setup_test_environment(self) -> bool:
        """Setup test environment and start server"""
        logger.info("Setting up test environment...")
        
        # Check if server is already running
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.server_url}/health", timeout=5) as response:
                    if response.status == 200:
                        logger.info("Server already running - using existing instance")
                        return True
        except:
            pass
        
        # Try to start server locally first
        if await self.start_local_server():
            return True
        
        # Fall back to Docker if available
        if self.docker_client and await self.start_docker_server():
            return True
        
        logger.error("Failed to start test server")
        return False
    
    async def start_local_server(self) -> bool:
        """Start server locally using uvx"""
        try:
            # Check if required environment variables are set
            if not os.environ.get('TELNYX_API_KEY'):
                logger.warning("TELNYX_API_KEY not set - skipping local server start")
                return False
            
            # Start server process
            cmd = [
                'uvx', 
                'awslabs.openapi-mcp-server@latest',
                '--host', '0.0.0.0',
                '--port', '8080',
                '--api-spec-path', str(self.project_path / 'telnyx.yml'),
                '--api-name', 'telnyx',
                '--api-base-url', 'https://api.telnyx.com/v2'
            ]
            
            self.server_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=str(self.project_path)
            )
            
            # Wait for server to start
            await asyncio.sleep(5)
            
            # Check if server is running
            if self.server_process.poll() is None:
                try:
                    async with aiohttp.ClientSession() as session:
                        async with session.get(f"{self.server_url}/health", timeout=5) as response:
                            if response.status == 200:
                                logger.info("Local server started successfully")
                                return True
                except:
                    pass
            
            # Server failed to start
            self.server_process.terminate()
            self.server_process = None
            return False
            
        except Exception as e:
            logger.error(f"Failed to start local server: {e}")
            return False
    
    async def start_docker_server(self) -> bool:
        """Start server using Docker"""
        try:
            # Build Docker image
            logger.info("Building Docker image for testing...")
            image, build_logs = self.docker_client.images.build(
                path=str(self.project_path),
                dockerfile='deployment/Dockerfile',
                tag='telnyx-mcp-test:latest',
                rm=True
            )
            
            # Start container
            logger.info("Starting Docker container...")
            self.docker_container = self.docker_client.containers.run(
                image.id,
                detach=True,
                ports={'8080/tcp': 8080},
                environment={
                    'TELNYX_API_KEY': os.environ.get('TELNYX_API_KEY', 'test-key'),
                    'LOG_LEVEL': 'INFO'
                },
                name='telnyx-mcp-test'
            )
            
            # Wait for container to start
            await asyncio.sleep(10)
            
            # Check if container is running and server is responding
            if self.docker_container.status == 'running':
                try:
                    async with aiohttp.ClientSession() as session:
                        async with session.get(f"{self.server_url}/health", timeout=5) as response:
                            if response.status == 200:
                                logger.info("Docker server started successfully")
                                return True
                except:
                    pass
            
            # Container failed to start properly
            self.docker_container.stop()
            self.docker_container.remove()
            self.docker_container = None
            return False
            
        except Exception as e:
            logger.error(f"Failed to start Docker server: {e}")
            return False
    
    async def cleanup_test_environment(self):
        """Cleanup test environment"""
        logger.info("Cleaning up test environment...")
        
        # Stop local server process
        if self.server_process:
            try:
                self.server_process.terminate()
                self.server_process.wait(timeout=10)
            except:
                self.server_process.kill()
            self.server_process = None
        
        # Stop and remove Docker container
        if self.docker_container:
            try:
                self.docker_container.stop(timeout=5)
                self.docker_container.remove()
            except:
                pass
            self.docker_container = None
        
        # Clean up Docker images
        if self.docker_client:
            try:
                self.docker_client.images.remove('telnyx-mcp-test:latest', force=True)
            except:
                pass
    
    async def test_server_health(self) -> TestResult:
        """Test server health endpoint"""
        start_time = time.time()
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.server_url}/health", timeout=10) as response:
                    duration = time.time() - start_time
                    
                    if response.status == 200:
                        return TestResult(
                            test_name="Server Health Check",
                            status="pass",
                            message="Health endpoint responding correctly",
                            duration_seconds=duration,
                            details={"status_code": response.status}
                        )
                    else:
                        return TestResult(
                            test_name="Server Health Check",
                            status="fail",
                            message=f"Health endpoint returned status {response.status}",
                            duration_seconds=duration,
                            details={"status_code": response.status}
                        )
        except Exception as e:
            return TestResult(
                test_name="Server Health Check",
                status="fail",
                message=f"Health check failed: {str(e)}",
                duration_seconds=time.time() - start_time
            )
    
    async def test_mcp_capabilities(self) -> TestResult:
        """Test MCP capabilities endpoints"""
        start_time = time.time()
        
        try:
            capabilities = {}
            endpoints_to_test = ['/tools', '/resources', '/prompts']
            
            async with aiohttp.ClientSession() as session:
                for endpoint in endpoints_to_test:
                    try:
                        async with session.get(f"{self.server_url}{endpoint}", timeout=10) as response:
                            if response.status == 200:
                                data = await response.json()
                                capabilities[endpoint] = {
                                    'status': response.status,
                                    'count': len(data.get(endpoint.strip('/'), []))
                                }
                            else:
                                capabilities[endpoint] = {
                                    'status': response.status,
                                    'error': f'HTTP {response.status}'
                                }
                    except Exception as e:
                        capabilities[endpoint] = {
                            'error': str(e)
                        }
            
            duration = time.time() - start_time
            
            # Check if at least one endpoint worked
            successful_endpoints = [ep for ep, data in capabilities.items() if data.get('status') == 200]
            
            if successful_endpoints:
                total_tools = sum(data.get('count', 0) for data in capabilities.values() if 'count' in data)
                return TestResult(
                    test_name="MCP Capabilities",
                    status="pass",
                    message=f"MCP endpoints responding ({total_tools} total items)",
                    duration_seconds=duration,
                    details=capabilities
                )
            else:
                return TestResult(
                    test_name="MCP Capabilities",
                    status="fail",
                    message="No MCP endpoints responding correctly",
                    duration_seconds=duration,
                    details=capabilities
                )
                
        except Exception as e:
            return TestResult(
                test_name="MCP Capabilities",
                status="fail",
                message=f"MCP capabilities test failed: {str(e)}",
                duration_seconds=time.time() - start_time
            )
    
    async def test_api_authentication(self) -> TestResult:
        """Test API authentication configuration"""
        start_time = time.time()
        
        # This test validates that the server properly handles authentication
        # by making a request that would require valid Telnyx API credentials
        
        try:
            # Try to access a protected endpoint that would require authentication
            test_payload = {
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {
                    "name": "list_phone_numbers",
                    "arguments": {}
                },
                "id": 1
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.server_url}/mcp",
                    json=test_payload,
                    headers={'Content-Type': 'application/json'},
                    timeout=15
                ) as response:
                    duration = time.time() - start_time
                    response_data = await response.json()
                    
                    # We expect either:
                    # - Success (200) if API key is valid
                    # - Unauthorized (401) if API key is invalid but server is working
                    # - Error response but proper JSON-RPC format
                    
                    if response.status in [200, 401, 403]:
                        if 'jsonrpc' in response_data:
                            return TestResult(
                                test_name="API Authentication",
                                status="pass",
                                message="Server properly handles authentication",
                                duration_seconds=duration,
                                details={
                                    "status_code": response.status,
                                    "response": response_data
                                }
                            )
                    
                    return TestResult(
                        test_name="API Authentication",
                        status="warning",
                        message=f"Unexpected response format (status: {response.status})",
                        duration_seconds=duration,
                        details={"status_code": response.status, "response": response_data}
                    )
                    
        except asyncio.TimeoutError:
            return TestResult(
                test_name="API Authentication",
                status="fail",
                message="Authentication test timed out",
                duration_seconds=time.time() - start_time
            )
        except Exception as e:
            return TestResult(
                test_name="API Authentication",
                status="fail",
                message=f"Authentication test failed: {str(e)}",
                duration_seconds=time.time() - start_time
            )
    
    async def test_performance(self) -> TestResult:
        """Test server performance with multiple requests"""
        start_time = time.time()
        
        try:
            # Make multiple concurrent requests to test performance
            async with aiohttp.ClientSession() as session:
                tasks = []
                
                # Create 10 concurrent health check requests
                for i in range(10):
                    task = session.get(f"{self.server_url}/health")
                    tasks.append(task)
                
                # Execute requests concurrently
                responses = await asyncio.gather(*tasks, return_exceptions=True)
                
                # Analyze results
                successful_requests = 0
                total_response_time = 0
                
                for response in responses:
                    if isinstance(response, aiohttp.ClientResponse):
                        if response.status == 200:
                            successful_requests += 1
                        response.close()
                
                duration = time.time() - start_time
                avg_response_time = duration / len(tasks)
                
                if successful_requests >= 8:  # At least 80% success rate
                    return TestResult(
                        test_name="Performance Test",
                        status="pass",
                        message=f"Performance test passed ({successful_requests}/{len(tasks)} requests successful)",
                        duration_seconds=duration,
                        details={
                            "total_requests": len(tasks),
                            "successful_requests": successful_requests,
                            "avg_response_time": avg_response_time,
                            "success_rate": successful_requests / len(tasks)
                        }
                    )
                else:
                    return TestResult(
                        test_name="Performance Test",
                        status="fail",
                        message=f"Performance test failed ({successful_requests}/{len(tasks)} requests successful)",
                        duration_seconds=duration,
                        details={
                            "total_requests": len(tasks),
                            "successful_requests": successful_requests,
                            "avg_response_time": avg_response_time,
                            "success_rate": successful_requests / len(tasks)
                        }
                    )
                    
        except Exception as e:
            return TestResult(
                test_name="Performance Test",
                status="fail",
                message=f"Performance test failed: {str(e)}",
                duration_seconds=time.time() - start_time
            )
    
    async def test_error_handling(self) -> TestResult:
        """Test server error handling"""
        start_time = time.time()
        
        try:
            error_scenarios = []
            
            async with aiohttp.ClientSession() as session:
                # Test invalid endpoint
                try:
                    async with session.get(f"{self.server_url}/invalid-endpoint", timeout=5) as response:
                        error_scenarios.append({
                            "test": "invalid_endpoint",
                            "status": response.status,
                            "handled_gracefully": response.status in [404, 405]
                        })
                except Exception as e:
                    error_scenarios.append({
                        "test": "invalid_endpoint",
                        "error": str(e),
                        "handled_gracefully": False
                    })
                
                # Test malformed JSON request
                try:
                    async with session.post(
                        f"{self.server_url}/mcp",
                        data="invalid json",
                        headers={'Content-Type': 'application/json'},
                        timeout=5
                    ) as response:
                        error_scenarios.append({
                            "test": "malformed_json",
                            "status": response.status,
                            "handled_gracefully": response.status in [400, 422]
                        })
                except Exception as e:
                    error_scenarios.append({
                        "test": "malformed_json",
                        "error": str(e),
                        "handled_gracefully": False
                    })
            
            duration = time.time() - start_time
            
            # Check if errors were handled gracefully
            graceful_handling = all(scenario.get('handled_gracefully', False) for scenario in error_scenarios)
            
            if graceful_handling:
                return TestResult(
                    test_name="Error Handling",
                    status="pass",
                    message="Server handles errors gracefully",
                    duration_seconds=duration,
                    details={"error_scenarios": error_scenarios}
                )
            else:
                return TestResult(
                    test_name="Error Handling",
                    status="fail",
                    message="Server does not handle all errors gracefully",
                    duration_seconds=duration,
                    details={"error_scenarios": error_scenarios}
                )
                
        except Exception as e:
            return TestResult(
                test_name="Error Handling",
                status="fail",
                message=f"Error handling test failed: {str(e)}",
                duration_seconds=time.time() - start_time
            )
    
    async def run_integration_tests(self) -> Dict[str, Any]:
        """Run complete integration test suite"""
        logger.info("Starting Telnyx MCP Server integration tests...")
        
        # Setup test environment
        if not await self.setup_test_environment():
            return {
                'timestamp': str(datetime.now()),
                'overall_status': 'fail',
                'message': 'Failed to setup test environment',
                'results': []
            }
        
        try:
            # Define test cases
            test_cases = [
                self.test_server_health,
                self.test_mcp_capabilities,
                self.test_api_authentication,
                self.test_performance,
                self.test_error_handling
            ]
            
            results = []
            
            # Run each test case
            for test_case in test_cases:
                try:
                    logger.info(f"Running {test_case.__name__}...")
                    result = await test_case()
                    results.append(result)
                    
                    status_icon = {
                        'pass': '✅',
                        'warning': '⚠️',
                        'fail': '❌',
                        'skip': '⏭️'
                    }.get(result.status, '❓')
                    
                    logger.info(f"{status_icon} {result.test_name}: {result.message} ({result.duration_seconds:.1f}s)")
                    
                except Exception as e:
                    logger.error(f"Test case {test_case.__name__} failed: {e}")
                    results.append(TestResult(
                        test_name=test_case.__name__.replace('test_', '').replace('_', ' ').title(),
                        status="fail",
                        message=f"Test execution failed: {str(e)}",
                        duration_seconds=0.0
                    ))
            
            # Calculate summary
            total_tests = len(results)
            passed_tests = len([r for r in results if r.status == 'pass'])
            failed_tests = len([r for r in results if r.status == 'fail'])
            warning_tests = len([r for r in results if r.status == 'warning'])
            
            # Determine overall status
            if failed_tests > 0:
                overall_status = 'fail'
            elif warning_tests > 0:
                overall_status = 'warning'
            else:
                overall_status = 'pass'
            
            return {
                'timestamp': str(datetime.now()),
                'overall_status': overall_status,
                'summary': {
                    'total_tests': total_tests,
                    'passed': passed_tests,
                    'failed': failed_tests,
                    'warnings': warning_tests
                },
                'results': [
                    {
                        'test_name': r.test_name,
                        'status': r.status,
                        'message': r.message,
                        'duration_seconds': r.duration_seconds,
                        'details': r.details
                    } for r in results
                ]
            }
            
        finally:
            # Always cleanup
            await self.cleanup_test_environment()

async def main():
    """Main entry point"""
    import argparse
    from datetime import datetime
    
    parser = argparse.ArgumentParser(description='Telnyx MCP Server Integration Tests')
    parser.add_argument('--server-url', default='http://localhost:8080',
                       help='MCP Server URL (default: http://localhost:8080)')
    parser.add_argument('--project-path', default='.',
                       help='Path to project directory (default: current directory)')
    parser.add_argument('--json', action='store_true',
                       help='Output results in JSON format')
    parser.add_argument('--fail-on-warnings', action='store_true',
                       help='Exit with code 1 if warnings found')
    
    args = parser.parse_args()
    
    test_suite = TelnyxMCPIntegrationTest(args.server_url, args.project_path)
    report = await test_suite.run_integration_tests()
    
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"\n=== Telnyx MCP Server Integration Test Report ===")
        print(f"Timestamp: {report['timestamp']}")
        print(f"Overall Status: {report['overall_status'].upper()}")
        
        if 'summary' in report:
            summary = report['summary']
            print(f"\n=== Summary ===")
            print(f"Total Tests: {summary['total_tests']}")
            print(f"✅ Passed: {summary['passed']}")
            print(f"❌ Failed: {summary['failed']}")
            print(f"⚠️  Warnings: {summary['warnings']}")
        
        if 'results' in report:
            print(f"\n=== Test Results ===")
            for result in report['results']:
                status_icon = {
                    'pass': '✅',
                    'warning': '⚠️',
                    'fail': '❌',
                    'skip': '⏭️'
                }.get(result['status'], '❓')
                
                print(f"{status_icon} {result['test_name']}: {result['message']} ({result['duration_seconds']:.1f}s)")
        
        if report['overall_status'] == 'pass':
            print(f"\n🎉 All integration tests passed!")
        else:
            print(f"\n⚠️  Some tests failed or had warnings. Review results above.")
    
    # Set exit code based on results
    if report['overall_status'] == 'fail':
        sys.exit(1)
    elif report['overall_status'] == 'warning' and args.fail_on_warnings:
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())