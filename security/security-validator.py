#!/usr/bin/env python3
"""
Security validation and hardening for Telnyx MCP Server
Validates configuration, checks for security issues, and provides recommendations
"""

import os
import re
import json
import sys
import subprocess
import logging
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
from pathlib import Path
import yaml

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

@dataclass
class SecurityFinding:
    """Security finding data structure"""
    severity: str  # critical, high, medium, low, info
    category: str  # authentication, authorization, network, container, etc.
    title: str
    description: str
    recommendation: str
    file_path: Optional[str] = None
    line_number: Optional[int] = None

class TelnyxMCPSecurityValidator:
    """Comprehensive security validator for Telnyx MCP Server"""
    
    def __init__(self, project_path: str):
        self.project_path = Path(project_path)
        self.findings: List[SecurityFinding] = []
        
        # Security patterns and rules
        self.dangerous_patterns = {
            # Secret exposure patterns
            r'(?i)(password|passwd|pwd|secret|key|token|api[_-]?key)\s*[:=]\s*["\']?[a-zA-Z0-9]{8,}': 'potential_secret_exposure',
            r'KEY[a-zA-Z0-9_-]{20,}': 'telnyx_api_key_exposure',
            r'sk_[a-zA-Z0-9]{20,}': 'stripe_key_exposure',
            r'AKIA[0-9A-Z]{16}': 'aws_access_key_exposure',
            
            # Command injection patterns
            r'os\.system\s*\(': 'command_injection_risk',
            r'subprocess\.(call|run|Popen)\s*\([^)]*shell\s*=\s*True': 'shell_injection_risk',
            r'eval\s*\(': 'code_injection_risk',
            r'exec\s*\(': 'code_injection_risk',
            
            # Insecure network patterns
            r'http://[^/\s]+': 'insecure_http_usage',
            r'ssl_verify\s*[:=]\s*False': 'ssl_verification_disabled',
            r'verify\s*=\s*False': 'ssl_verification_disabled',
            
            # Insecure configurations
            r'DEBUG\s*[:=]\s*True': 'debug_mode_enabled',
            r'--insecure': 'insecure_flag_usage',
        }
    
    def validate_environment_variables(self) -> List[SecurityFinding]:
        """Validate environment variable configuration"""
        findings = []
        
        # Check for required environment variables
        required_vars = ['TELNYX_API_KEY']
        optional_secure_vars = ['LOG_LEVEL', 'API_BASE_URL']
        
        for var in required_vars:
            value = os.environ.get(var)
            if not value:
                findings.append(SecurityFinding(
                    severity='critical',
                    category='authentication',
                    title=f'Missing required environment variable: {var}',
                    description=f'The required environment variable {var} is not set',
                    recommendation=f'Set the {var} environment variable with a valid value'
                ))
            elif var == 'TELNYX_API_KEY':
                # Validate Telnyx API key format
                if not value.startswith('KEY'):
                    findings.append(SecurityFinding(
                        severity='high',
                        category='authentication',
                        title='Invalid Telnyx API key format',
                        description='TELNYX_API_KEY does not start with "KEY" as expected',
                        recommendation='Ensure TELNYX_API_KEY is a valid Telnyx API key starting with "KEY"'
                    ))
                elif len(value) < 20:
                    findings.append(SecurityFinding(
                        severity='medium',
                        category='authentication',
                        title='Potentially invalid Telnyx API key',
                        description='TELNYX_API_KEY appears to be too short',
                        recommendation='Verify that TELNYX_API_KEY is a complete, valid API key'
                    ))
        
        # Check for insecure environment variable usage
        for var_name, var_value in os.environ.items():
            if var_name.upper() in ['PASSWORD', 'SECRET', 'TOKEN'] and var_value:
                findings.append(SecurityFinding(
                    severity='medium',
                    category='authentication',
                    title=f'Sensitive data in environment variable: {var_name}',
                    description='Sensitive data should not be stored in plain environment variables',
                    recommendation='Use secrets management or encrypted configuration instead'
                ))
        
        return findings
    
    def scan_source_code(self) -> List[SecurityFinding]:
        """Scan source code for security issues"""
        findings = []
        
        # File extensions to scan
        extensions = ['.py', '.js', '.ts', '.sh', '.yaml', '.yml', '.json', '.dockerfile']
        
        # Files to exclude from scanning (security tools, test files, etc.)
        exclude_patterns = [
            'security/security-validator.py',
            'security/secrets-manager.py', 
            'tests/',
            'monitoring/',
            '.git/',
            '__pycache__/',
            '.pytest_cache/',
            'node_modules/',
            'telnyx.yml',  # OpenAPI spec file contains example data
            'deploy.sh'   # Deployment script may contain example URLs
        ]
        
        for ext in extensions:
            for file_path in self.project_path.rglob(f'*{ext}'):
                # Skip excluded files
                relative_path = str(file_path.relative_to(self.project_path))
                if any(exclude in relative_path for exclude in exclude_patterns):
                    continue
                    
                try:
                    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read()
                        findings.extend(self._scan_file_content(file_path, content))
                except Exception as e:
                    logger.warning(f"Could not scan file {file_path}: {e}")
        
        return findings
    
    def _scan_file_content(self, file_path: Path, content: str) -> List[SecurityFinding]:
        """Scan individual file content for security issues"""
        findings = []
        lines = content.split('\n')
        
        for line_num, line in enumerate(lines, 1):
            # Skip lines that are clearly examples or documentation
            line_lower = line.lower()
            if any(keyword in line_lower for keyword in ['example', 'sample', 'placeholder', 'xxx', '123', 'abc', 'def']):
                continue
            
            for pattern, issue_type in self.dangerous_patterns.items():
                if re.search(pattern, line):
                    severity, title, description, recommendation = self._get_issue_details(issue_type, line)
                    findings.append(SecurityFinding(
                        severity=severity,
                        category=self._get_category(issue_type),
                        title=title,
                        description=description,
                        recommendation=recommendation,
                        file_path=str(file_path.relative_to(self.project_path)),
                        line_number=line_num
                    ))
        
        return findings
    
    def _get_issue_details(self, issue_type: str, line: str) -> Tuple[str, str, str, str]:
        """Get detailed information about a security issue"""
        issue_details = {
            'potential_secret_exposure': (
                'high',
                'Potential secret exposure in source code',
                f'Line contains what appears to be a hardcoded secret: {line.strip()[:50]}...',
                'Move secrets to environment variables or secure configuration'
            ),
            'telnyx_api_key_exposure': (
                'critical',
                'Telnyx API key exposed in source code',
                'Telnyx API key found in source code',
                'Remove API key from source code and use environment variables'
            ),
            'stripe_key_exposure': (
                'critical',
                'Stripe API key exposed in source code',
                'Stripe API key found in source code',
                'Remove API key from source code and use environment variables'
            ),
            'aws_access_key_exposure': (
                'critical',
                'AWS access key exposed in source code',
                'AWS access key found in source code',
                'Remove access key from source code and use IAM roles or environment variables'
            ),
            'command_injection_risk': (
                'high',
                'Command injection vulnerability risk',
                'Use of os.system() can lead to command injection',
                'Use subprocess with shell=False or parameterized commands'
            ),
            'shell_injection_risk': (
                'high',
                'Shell injection vulnerability risk',
                'Use of shell=True in subprocess can lead to injection',
                'Use subprocess without shell=True or validate input thoroughly'
            ),
            'code_injection_risk': (
                'critical',
                'Code injection vulnerability risk',
                'Use of eval() or exec() can lead to code injection',
                'Avoid eval() and exec(); use safer alternatives for dynamic code execution'
            ),
            'insecure_http_usage': (
                'medium',
                'Insecure HTTP usage',
                'HTTP URLs found - data transmitted in plaintext',
                'Use HTTPS URLs for secure communication'
            ),
            'ssl_verification_disabled': (
                'high',
                'SSL verification disabled',
                'SSL certificate verification is disabled',
                'Enable SSL verification for secure connections'
            ),
            'debug_mode_enabled': (
                'medium',
                'Debug mode enabled',
                'Debug mode can expose sensitive information',
                'Disable debug mode in production environments'
            ),
            'insecure_flag_usage': (
                'medium',
                'Insecure flag usage',
                'Insecure flags found in configuration',
                'Remove insecure flags from production configuration'
            ),
        }
        
        return issue_details.get(issue_type, (
            'info',
            'Security consideration',
            'Potential security issue detected',
            'Review and assess security implications'
        ))
    
    def _get_category(self, issue_type: str) -> str:
        """Get security category for issue type"""
        categories = {
            'potential_secret_exposure': 'secrets',
            'telnyx_api_key_exposure': 'secrets',
            'stripe_key_exposure': 'secrets',
            'aws_access_key_exposure': 'secrets',
            'command_injection_risk': 'injection',
            'shell_injection_risk': 'injection',
            'code_injection_risk': 'injection',
            'insecure_http_usage': 'network',
            'ssl_verification_disabled': 'network',
            'debug_mode_enabled': 'configuration',
            'insecure_flag_usage': 'configuration',
        }
        return categories.get(issue_type, 'general')
    
    def validate_container_security(self) -> List[SecurityFinding]:
        """Validate container security configuration"""
        findings = []
        
        dockerfile_path = self.project_path / 'deployment' / 'Dockerfile'
        if dockerfile_path.exists():
            try:
                with open(dockerfile_path, 'r') as f:
                    content = f.read()
                    findings.extend(self._validate_dockerfile_security(content, dockerfile_path))
            except Exception as e:
                logger.warning(f"Could not validate Dockerfile: {e}")
        
        return findings
    
    def _validate_dockerfile_security(self, content: str, file_path: Path) -> List[SecurityFinding]:
        """Validate Dockerfile security best practices"""
        findings = []
        lines = content.split('\n')
        
        has_non_root_user = False
        runs_as_root = False
        
        for line_num, line in enumerate(lines, 1):
            line = line.strip()
            
            # Check for non-root user
            if re.match(r'^USER\s+(?!root)', line):
                has_non_root_user = True
            elif re.match(r'^USER\s+root', line):
                runs_as_root = True
            
            # Check for package update without cleanup
            if re.search(r'apt-get\s+update.*&&.*apt-get\s+install', line):
                if 'rm -rf /var/lib/apt/lists/*' not in line and 'rm -rf /var/lib/apt/lists/*' not in content:
                    findings.append(SecurityFinding(
                        severity='low',
                        category='container',
                        title='Package cache not cleaned up',
                        description='Package manager cache should be cleaned to reduce image size',
                        recommendation='Add "rm -rf /var/lib/apt/lists/*" after package installation',
                        file_path=str(file_path.relative_to(self.project_path)),
                        line_number=line_num
                    ))
            
            # Check for COPY/ADD with overly broad permissions
            if re.match(r'^(COPY|ADD).*--chown=root', line):
                findings.append(SecurityFinding(
                    severity='medium',
                    category='container',
                    title='Files copied with root ownership',
                    description='Files should not be owned by root unless necessary',
                    recommendation='Use a non-root user for file ownership',
                    file_path=str(file_path.relative_to(self.project_path)),
                    line_number=line_num
                ))
        
        # Check if container runs as root
        if not has_non_root_user or runs_as_root:
            findings.append(SecurityFinding(
                severity='high',
                category='container',
                title='Container runs as root user',
                description='Container should run as a non-root user for security',
                recommendation='Add a non-root user and use USER directive',
                file_path=str(file_path.relative_to(self.project_path))
            ))
        
        return findings
    
    def validate_configuration_files(self) -> List[SecurityFinding]:
        """Validate configuration file security"""
        findings = []
        
        # Check smithery.yaml
        smithery_yaml = self.project_path / 'smithery.yaml'
        if smithery_yaml.exists():
            try:
                with open(smithery_yaml, 'r') as f:
                    config = yaml.safe_load(f)
                    findings.extend(self._validate_smithery_config(config, smithery_yaml))
            except Exception as e:
                logger.warning(f"Could not validate smithery.yaml: {e}")
        
        # Check smithery.json
        smithery_json = self.project_path / 'smithery.json'
        if smithery_json.exists():
            try:
                with open(smithery_json, 'r') as f:
                    config = json.load(f)
                    findings.extend(self._validate_smithery_json_config(config, smithery_json))
            except Exception as e:
                logger.warning(f"Could not validate smithery.json: {e}")
        
        return findings
    
    def _validate_smithery_config(self, config: Dict[str, Any], file_path: Path) -> List[SecurityFinding]:
        """Validate smithery.yaml security configuration"""
        findings = []
        
        # Check security settings
        if 'deployment' in config:
            deployment = config['deployment']
            if 'security' in deployment:
                security = deployment['security']
                
                if not security.get('readOnlyRootFilesystem', False):
                    findings.append(SecurityFinding(
                        severity='medium',
                        category='container',
                        title='Root filesystem not read-only',
                        description='Container should use read-only root filesystem',
                        recommendation='Set deployment.security.readOnlyRootFilesystem to true',
                        file_path=str(file_path.relative_to(self.project_path))
                    ))
                
                if security.get('runAsNonRoot', True) is False:
                    findings.append(SecurityFinding(
                        severity='high',
                        category='container',
                        title='Container configured to run as root',
                        description='Container should not run as root user',
                        recommendation='Set deployment.security.runAsNonRoot to true',
                        file_path=str(file_path.relative_to(self.project_path))
                    ))
        
        # Check for insecure configuration
        if 'networking' in config:
            networking = config['networking']
            if 'ingress' in networking:
                ingress = networking['ingress']
                if ingress.get('tls', True) is False:
                    findings.append(SecurityFinding(
                        severity='high',
                        category='network',
                        title='TLS disabled for ingress',
                        description='Ingress should use TLS encryption',
                        recommendation='Set networking.ingress.tls to true',
                        file_path=str(file_path.relative_to(self.project_path))
                    ))
        
        return findings
    
    def _validate_smithery_json_config(self, config: Dict[str, Any], file_path: Path) -> List[SecurityFinding]:
        """Validate smithery.json security configuration"""
        findings = []
        
        # Check authentication configuration
        if 'authentication' in config:
            auth = config['authentication']
            if not auth.get('required', False):
                findings.append(SecurityFinding(
                    severity='high',
                    category='authentication',
                    title='Authentication not required',
                    description='Server should require authentication',
                    recommendation='Set authentication.required to true',
                    file_path=str(file_path.relative_to(self.project_path))
                ))
        
        # Check security section
        if 'security' in config:
            security = config['security']
            data_handling = security.get('dataHandling', {})
            
            if data_handling.get('pii', False) and security.get('encryption') != 'in-transit':
                findings.append(SecurityFinding(
                    severity='medium',
                    category='data',
                    title='PII handling without proper encryption',
                    description='PII data should be encrypted in transit and at rest',
                    recommendation='Ensure proper encryption is configured for PII data',
                    file_path=str(file_path.relative_to(self.project_path))
                ))
        
        return findings
    
    def generate_security_report(self) -> Dict[str, Any]:
        """Generate comprehensive security report"""
        logger.info("Starting security validation...")
        
        # Run all security checks
        self.findings.extend(self.validate_environment_variables())
        self.findings.extend(self.scan_source_code())
        self.findings.extend(self.validate_container_security())
        self.findings.extend(self.validate_configuration_files())
        
        # Categorize findings by severity
        severity_counts = {}
        category_counts = {}
        
        for finding in self.findings:
            severity_counts[finding.severity] = severity_counts.get(finding.severity, 0) + 1
            category_counts[finding.category] = category_counts.get(finding.category, 0) + 1
        
        # Calculate security score (100 - deductions)
        score = 100
        for finding in self.findings:
            if finding.severity == 'critical':
                score -= 30
            elif finding.severity == 'high':
                score -= 20
            elif finding.severity == 'medium':
                score -= 10
            elif finding.severity == 'low':
                score -= 5
        
        score = max(0, score)
        
        return {
            'timestamp': str(datetime.now()),
            'security_score': score,
            'total_findings': len(self.findings),
            'severity_breakdown': severity_counts,
            'category_breakdown': category_counts,
            'findings': [
                {
                    'severity': f.severity,
                    'category': f.category,
                    'title': f.title,
                    'description': f.description,
                    'recommendation': f.recommendation,
                    'file_path': f.file_path,
                    'line_number': f.line_number
                }
                for f in self.findings
            ]
        }

def main():
    """Main entry point"""
    import argparse
    from datetime import datetime
    
    parser = argparse.ArgumentParser(description='Telnyx MCP Server Security Validator')
    parser.add_argument('--project-path', default='.', 
                       help='Path to project directory (default: current directory)')
    parser.add_argument('--json', action='store_true',
                       help='Output results in JSON format')
    parser.add_argument('--fail-on-critical', action='store_true',
                       help='Exit with code 1 if critical issues found')
    parser.add_argument('--fail-on-high', action='store_true',
                       help='Exit with code 1 if high severity issues found')
    
    args = parser.parse_args()
    
    validator = TelnyxMCPSecurityValidator(args.project_path)
    report = validator.generate_security_report()
    
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"\n=== Telnyx MCP Server Security Report ===")
        print(f"Security Score: {report['security_score']}/100")
        print(f"Total Findings: {report['total_findings']}")
        
        if report['severity_breakdown']:
            print("\n=== Severity Breakdown ===")
            for severity, count in sorted(report['severity_breakdown'].items()):
                icon = {"critical": "🚨", "high": "⚠️", "medium": "⚡", "low": "ℹ️", "info": "📋"}.get(severity, "•")
                print(f"{icon} {severity.title()}: {count}")
        
        if report['category_breakdown']:
            print("\n=== Category Breakdown ===")
            for category, count in sorted(report['category_breakdown'].items()):
                print(f"• {category.title()}: {count}")
        
        if report['findings']:
            print("\n=== Findings ===")
            for finding in report['findings']:
                severity_icon = {
                    "critical": "🚨", "high": "⚠️", "medium": "⚡", 
                    "low": "ℹ️", "info": "📋"
                }.get(finding['severity'], "•")
                
                print(f"\n{severity_icon} {finding['title']} ({finding['severity']})")
                print(f"   Category: {finding['category']}")
                print(f"   Description: {finding['description']}")
                print(f"   Recommendation: {finding['recommendation']}")
                
                if finding['file_path']:
                    location = finding['file_path']
                    if finding['line_number']:
                        location += f":{finding['line_number']}"
                    print(f"   Location: {location}")
        else:
            print("\n✅ No security issues found!")
    
    # Set exit code based on findings
    if args.fail_on_critical and 'critical' in report['severity_breakdown']:
        sys.exit(1)
    elif args.fail_on_high and ('critical' in report['severity_breakdown'] or 'high' in report['severity_breakdown']):
        sys.exit(1)

if __name__ == "__main__":
    main()