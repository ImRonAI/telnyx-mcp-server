#!/usr/bin/env python3
"""
Comprehensive deployment validation for Telnyx MCP Server
Validates deployment configuration, dependencies, and readiness for production
"""

import asyncio
import aiohttp
import docker
import json
import logging
import os
import subprocess
import sys
import time
import yaml
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

@dataclass
class ValidationResult:
    """Validation result data structure"""
    check_name: str
    status: str  # pass, fail, warning, skip
    message: str
    details: Optional[Dict[str, Any]] = None
    duration_seconds: Optional[float] = None

class TelnyxMCPDeploymentValidator:
    """Comprehensive deployment validator for Telnyx MCP Server"""
    
    def __init__(self, project_path: str = "."):
        self.project_path = Path(project_path).resolve()
        self.results: List[ValidationResult] = []
        self.docker_client = None
        
        # Initialize Docker client
        try:
            self.docker_client = docker.from_env()
        except Exception as e:
            logger.warning(f"Docker client initialization failed: {e}")
    
    async def validate_project_structure(self) -> ValidationResult:
        """Validate project directory structure and required files"""
        start_time = time.time()
        
        required_files = [
            'telnyx.yml',
            'smithery.yaml',
            'smithery.json',
            'deployment/Dockerfile',
            'pyproject.toml'
        ]
        
        optional_files = [
            'README.md',
            '.gitignore',
            'monitoring/health-monitor.py',
            'security/security-validator.py',
            'security/secrets-manager.py'
        ]
        
        missing_required = []
        missing_optional = []
        
        for file_path in required_files:
            full_path = self.project_path / file_path
            if not full_path.exists():
                missing_required.append(file_path)
        
        for file_path in optional_files:
            full_path = self.project_path / file_path
            if not full_path.exists():
                missing_optional.append(file_path)
        
        duration = time.time() - start_time
        
        if missing_required:
            return ValidationResult(
                check_name="Project Structure",
                status="fail",
                message=f"Missing required files: {', '.join(missing_required)}",
                details={
                    "missing_required": missing_required,
                    "missing_optional": missing_optional
                },
                duration_seconds=duration
            )
        else:
            return ValidationResult(
                check_name="Project Structure",
                status="pass",
                message="All required files present",
                details={
                    "missing_optional": missing_optional
                },
                duration_seconds=duration
            )
    
    async def validate_configuration_files(self) -> ValidationResult:
        """Validate configuration files syntax and completeness"""
        start_time = time.time()
        issues = []
        
        # Validate smithery.yaml
        try:
            with open(self.project_path / 'smithery.yaml', 'r') as f:
                smithery_config = yaml.safe_load(f)
            
            required_sections = ['runtime', 'build', 'startCommand']
            for section in required_sections:
                if section not in smithery_config:
                    issues.append(f"smithery.yaml missing required section: {section}")
        except Exception as e:
            issues.append(f"smithery.yaml validation failed: {e}")
        
        # Validate smithery.json
        try:
            with open(self.project_path / 'smithery.json', 'r') as f:
                smithery_meta = json.load(f)
            
            required_fields = ['serverId', 'name', 'description', 'version']
            for field in required_fields:
                if field not in smithery_meta:
                    issues.append(f"smithery.json missing required field: {field}")
        except Exception as e:
            issues.append(f"smithery.json validation failed: {e}")
        
        # Validate telnyx.yml (basic check)
        try:
            telnyx_spec_path = self.project_path / 'telnyx.yml'
            if telnyx_spec_path.exists():
                with open(telnyx_spec_path, 'r') as f:
                    content = f.read()
                    if len(content) < 1000:  # Very small file is likely incomplete
                        issues.append("telnyx.yml appears to be incomplete (too small)")
            else:
                issues.append("telnyx.yml not found")
        except Exception as e:
            issues.append(f"telnyx.yml validation failed: {e}")
        
        duration = time.time() - start_time
        
        if issues:
            return ValidationResult(
                check_name="Configuration Files",
                status="fail",
                message=f"Configuration issues found: {len(issues)}",
                details={"issues": issues},
                duration_seconds=duration
            )
        else:
            return ValidationResult(
                check_name="Configuration Files",
                status="pass",
                message="All configuration files are valid",
                duration_seconds=duration
            )
    
    async def validate_docker_configuration(self) -> ValidationResult:
        """Validate Docker configuration and build capability"""
        start_time = time.time()
        
        if not self.docker_client:
            return ValidationResult(
                check_name="Docker Configuration",
                status="skip",
                message="Docker client not available",
                duration_seconds=time.time() - start_time
            )
        
        try:
            dockerfile_path = self.project_path / 'deployment' / 'Dockerfile'
            
            # Check if Dockerfile exists and is readable
            if not dockerfile_path.exists():
                return ValidationResult(
                    check_name="Docker Configuration",
                    status="fail",
                    message="Dockerfile not found at deployment/Dockerfile",
                    duration_seconds=time.time() - start_time
                )
            
            # Validate Dockerfile syntax by attempting a build (dry run)
            try:
                # Build the image
                logger.info("Building Docker image for validation...")
                image, build_logs = self.docker_client.images.build(
                    path=str(self.project_path),
                    dockerfile='deployment/Dockerfile',
                    tag='telnyx-mcp-test:latest',
                    rm=True,
                    forcerm=True
                )
                
                # Clean up the test image
                self.docker_client.images.remove(image.id, force=True)
                
                duration = time.time() - start_time
                return ValidationResult(
                    check_name="Docker Configuration",
                    status="pass",
                    message="Docker build successful",
                    details={"image_id": image.short_id},
                    duration_seconds=duration
                )
                
            except docker.errors.BuildError as e:
                return ValidationResult(
                    check_name="Docker Configuration",
                    status="fail",
                    message=f"Docker build failed: {str(e)}",
                    details={"build_error": str(e)},
                    duration_seconds=time.time() - start_time
                )
                
        except Exception as e:
            return ValidationResult(
                check_name="Docker Configuration",
                status="fail",
                message=f"Docker validation failed: {str(e)}",
                duration_seconds=time.time() - start_time
            )
    
    async def validate_dependencies(self) -> ValidationResult:
        """Validate project dependencies and requirements"""
        start_time = time.time()
        issues = []
        
        # Check if awslabs.openapi-mcp-server is available
        try:
            result = subprocess.run(
                ['uvx', '--help'], 
                capture_output=True, 
                text=True, 
                timeout=10
            )
            if result.returncode != 0:
                issues.append("uvx not available - required for OpenAPI MCP server")
        except (subprocess.TimeoutExpired, FileNotFoundError):
            issues.append("uvx not installed - required for OpenAPI MCP server")
        
        # Check if required Python packages are available
        required_packages = ['aiohttp', 'pyyaml']
        for package in required_packages:
            try:
                __import__(package)
            except ImportError:
                issues.append(f"Python package '{package}' not available")
        
        duration = time.time() - start_time
        
        if issues:
            return ValidationResult(
                check_name="Dependencies",
                status="warning",
                message=f"Some dependencies missing: {len(issues)}",
                details={"missing_dependencies": issues},
                duration_seconds=duration
            )
        else:
            return ValidationResult(
                check_name="Dependencies",
                status="pass",
                message="All dependencies available",
                duration_seconds=duration
            )
    
    async def validate_environment_configuration(self) -> ValidationResult:
        """Validate environment configuration and secrets"""
        start_time = time.time()
        issues = []
        warnings = []
        
        # Check for required environment variables
        required_env_vars = ['TELNYX_API_KEY']
        for var in required_env_vars:
            value = os.environ.get(var)
            if not value:
                issues.append(f"Required environment variable {var} not set")
            elif var == 'TELNYX_API_KEY' and not value.startswith('KEY'):
                issues.append(f"Environment variable {var} appears to have invalid format")
        
        # Check for recommended environment variables
        recommended_env_vars = ['LOG_LEVEL', 'API_BASE_URL']
        for var in recommended_env_vars:
            if not os.environ.get(var):
                warnings.append(f"Recommended environment variable {var} not set")
        
        duration = time.time() - start_time
        
        if issues:
            return ValidationResult(
                check_name="Environment Configuration",
                status="fail",
                message=f"Environment issues found: {len(issues)}",
                details={"issues": issues, "warnings": warnings},
                duration_seconds=duration
            )
        elif warnings:
            return ValidationResult(
                check_name="Environment Configuration",
                status="warning",
                message=f"Environment warnings: {len(warnings)}",
                details={"warnings": warnings},
                duration_seconds=duration
            )
        else:
            return ValidationResult(
                check_name="Environment Configuration",
                status="pass",
                message="Environment configuration is valid",
                duration_seconds=duration
            )
    
    async def validate_network_connectivity(self) -> ValidationResult:
        """Validate network connectivity to required services"""
        start_time = time.time()
        connectivity_results = {}
        
        # Test connectivity to Telnyx API
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get('https://api.telnyx.com/v2/', timeout=10) as response:
                    connectivity_results['telnyx_api'] = {
                        'status': response.status,
                        'reachable': True
                    }
        except Exception as e:
            connectivity_results['telnyx_api'] = {
                'error': str(e),
                'reachable': False
            }
        
        # Test connectivity to container registries (if needed)
        registry_endpoints = [
            'https://registry.hub.docker.com/',
            'https://index.docker.io/'
        ]
        
        for endpoint in registry_endpoints:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(endpoint, timeout=5) as response:
                        connectivity_results[endpoint] = {
                            'status': response.status,
                            'reachable': True
                        }
            except Exception as e:
                connectivity_results[endpoint] = {
                    'error': str(e),
                    'reachable': False
                }
        
        duration = time.time() - start_time
        
        # Check if critical services are reachable
        critical_failures = []
        if not connectivity_results.get('telnyx_api', {}).get('reachable', False):
            critical_failures.append('Telnyx API not reachable')
        
        if critical_failures:
            return ValidationResult(
                check_name="Network Connectivity",
                status="fail",
                message=f"Critical network failures: {', '.join(critical_failures)}",
                details=connectivity_results,
                duration_seconds=duration
            )
        else:
            return ValidationResult(
                check_name="Network Connectivity",
                status="pass",
                message="Network connectivity validated",
                details=connectivity_results,
                duration_seconds=duration
            )
    
    async def validate_security_configuration(self) -> ValidationResult:
        """Validate security configuration"""
        start_time = time.time()
        
        try:
            # Run security validator if available
            security_script = self.project_path / 'security' / 'security-validator.py'
            if security_script.exists():
                result = subprocess.run(
                    [sys.executable, str(security_script), '--project-path', str(self.project_path), '--json'],
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                
                if result.returncode == 0:
                    security_report = json.loads(result.stdout)
                    security_score = security_report.get('security_score', 0)
                    total_findings = security_report.get('total_findings', 0)
                    
                    duration = time.time() - start_time
                    
                    if security_score >= 80:
                        return ValidationResult(
                            check_name="Security Configuration",
                            status="pass",
                            message=f"Security score: {security_score}/100",
                            details=security_report,
                            duration_seconds=duration
                        )
                    elif security_score >= 60:
                        return ValidationResult(
                            check_name="Security Configuration",
                            status="warning",
                            message=f"Security score: {security_score}/100 (needs improvement)",
                            details=security_report,
                            duration_seconds=duration
                        )
                    else:
                        return ValidationResult(
                            check_name="Security Configuration",
                            status="fail",
                            message=f"Security score too low: {security_score}/100",
                            details=security_report,
                            duration_seconds=duration
                        )
                else:
                    return ValidationResult(
                        check_name="Security Configuration",
                        status="fail",
                        message="Security validation script failed",
                        details={"error": result.stderr},
                        duration_seconds=time.time() - start_time
                    )
            else:
                return ValidationResult(
                    check_name="Security Configuration",
                    status="skip",
                    message="Security validator not available",
                    duration_seconds=time.time() - start_time
                )
        
        except Exception as e:
            return ValidationResult(
                check_name="Security Configuration",
                status="fail",
                message=f"Security validation failed: {str(e)}",
                duration_seconds=time.time() - start_time
            )
    
    async def run_comprehensive_validation(self) -> Dict[str, Any]:
        """Run all validation checks"""
        logger.info("Starting comprehensive deployment validation...")
        
        # Define validation checks
        validation_checks = [
            self.validate_project_structure,
            self.validate_configuration_files,
            self.validate_dependencies,
            self.validate_environment_configuration,
            self.validate_network_connectivity,
            self.validate_security_configuration,
            self.validate_docker_configuration,  # This is intensive, run it last
        ]
        
        results = []
        
        for check in validation_checks:
            try:
                logger.info(f"Running {check.__name__}...")
                result = await check()
                results.append(result)
                
                status_icon = {
                    'pass': '✅',
                    'warning': '⚠️',
                    'fail': '❌',
                    'skip': '⏭️'
                }.get(result.status, '❓')
                
                logger.info(f"{status_icon} {result.check_name}: {result.message}")
                
            except Exception as e:
                logger.error(f"Validation check {check.__name__} failed: {e}")
                results.append(ValidationResult(
                    check_name=check.__name__.replace('validate_', '').replace('_', ' ').title(),
                    status="fail",
                    message=f"Validation check failed: {str(e)}"
                ))
        
        # Calculate summary
        total_checks = len(results)
        passed_checks = len([r for r in results if r.status == 'pass'])
        failed_checks = len([r for r in results if r.status == 'fail'])
        warning_checks = len([r for r in results if r.status == 'warning'])
        skipped_checks = len([r for r in results if r.status == 'skip'])
        
        # Determine overall status
        if failed_checks > 0:
            overall_status = 'fail'
        elif warning_checks > 0:
            overall_status = 'warning'
        else:
            overall_status = 'pass'
        
        return {
            'timestamp': str(datetime.now()),
            'overall_status': overall_status,
            'summary': {
                'total_checks': total_checks,
                'passed': passed_checks,
                'failed': failed_checks,
                'warnings': warning_checks,
                'skipped': skipped_checks
            },
            'results': [asdict(result) for result in results],
            'deployment_ready': overall_status in ['pass', 'warning'] and failed_checks == 0
        }

async def main():
    """Main entry point"""
    import argparse
    from datetime import datetime
    
    parser = argparse.ArgumentParser(description='Telnyx MCP Server Deployment Validator')
    parser.add_argument('--project-path', default='.', 
                       help='Path to project directory (default: current directory)')
    parser.add_argument('--json', action='store_true',
                       help='Output results in JSON format')
    parser.add_argument('--fail-on-warnings', action='store_true',
                       help='Exit with code 1 if warnings found')
    parser.add_argument('--skip-docker', action='store_true',
                       help='Skip Docker build validation (faster)')
    
    args = parser.parse_args()
    
    validator = TelnyxMCPDeploymentValidator(args.project_path)
    
    # Skip Docker validation if requested
    if args.skip_docker:
        validator.docker_client = None
    
    report = await validator.run_comprehensive_validation()
    
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"\n=== Telnyx MCP Server Deployment Validation Report ===")
        print(f"Timestamp: {report['timestamp']}")
        print(f"Overall Status: {report['overall_status'].upper()}")
        print(f"Deployment Ready: {'✅ YES' if report['deployment_ready'] else '❌ NO'}")
        
        summary = report['summary']
        print(f"\n=== Summary ===")
        print(f"Total Checks: {summary['total_checks']}")
        print(f"✅ Passed: {summary['passed']}")
        print(f"❌ Failed: {summary['failed']}")
        print(f"⚠️  Warnings: {summary['warnings']}")
        print(f"⏭️  Skipped: {summary['skipped']}")
        
        print(f"\n=== Detailed Results ===")
        for result in report['results']:
            status_icon = {
                'pass': '✅',
                'warning': '⚠️',
                'fail': '❌',
                'skip': '⏭️'
            }.get(result['status'], '❓')
            
            duration_str = f" ({result['duration_seconds']:.1f}s)" if result['duration_seconds'] else ""
            print(f"{status_icon} {result['check_name']}: {result['message']}{duration_str}")
            
            if result.get('details'):
                details = result['details']
                if isinstance(details, dict):
                    for key, value in details.items():
                        if isinstance(value, list) and value:
                            print(f"    {key}: {', '.join(str(v) for v in value[:3])}{'...' if len(value) > 3 else ''}")
                        elif not isinstance(value, (list, dict)):
                            print(f"    {key}: {value}")
        
        # Print recommendations
        failed_results = [r for r in report['results'] if r['status'] == 'fail']
        warning_results = [r for r in report['results'] if r['status'] == 'warning']
        
        if failed_results or warning_results:
            print(f"\n=== Recommendations ===")
            if failed_results:
                print("Critical issues to fix before deployment:")
                for result in failed_results:
                    print(f"  • {result['check_name']}: {result['message']}")
            
            if warning_results:
                print("Warnings to consider:")
                for result in warning_results:
                    print(f"  • {result['check_name']}: {result['message']}")
        
        if report['deployment_ready']:
            print(f"\n🎉 Deployment validation passed! Ready for production deployment.")
        else:
            print(f"\n⚠️  Deployment NOT ready. Please address the issues above.")
    
    # Set exit code based on results
    if report['overall_status'] == 'fail':
        sys.exit(1)
    elif report['overall_status'] == 'warning' and args.fail_on_warnings:
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())