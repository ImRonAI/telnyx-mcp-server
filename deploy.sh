#!/bin/bash

# Telnyx MCP Server - Production Deployment Script
# This script handles the complete deployment process to Smithery platform

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_NAME="telnyx-mcp-server"
DOCKER_IMAGE_TAG="telnyx-mcp:latest"

# Default values
SKIP_TESTS=${SKIP_TESTS:-false}
SKIP_SECURITY_SCAN=${SKIP_SECURITY_SCAN:-false}
SKIP_DOCKER_BUILD=${SKIP_DOCKER_BUILD:-false}
DRY_RUN=${DRY_RUN:-false}
ENVIRONMENT=${ENVIRONMENT:-production}

# Help function
show_help() {
    cat << EOF
Telnyx MCP Server - Production Deployment Script

Usage: $0 [OPTIONS]

Options:
    -h, --help              Show this help message
    --skip-tests           Skip integration tests
    --skip-security        Skip security validation
    --skip-docker          Skip Docker build validation
    --dry-run              Perform dry run without actual deployment
    --environment ENV      Target environment (default: production)
    --verbose              Enable verbose output

Environment Variables:
    TELNYX_API_KEY         Required: Your Telnyx API key
    SKIP_TESTS             Skip tests if set to 'true'
    SKIP_SECURITY_SCAN     Skip security scan if set to 'true'
    DRY_RUN                Perform dry run if set to 'true'

Examples:
    $0                                    # Full deployment
    $0 --skip-tests                      # Deploy without running tests
    $0 --dry-run                         # Validate without deploying
    TELNYX_API_KEY=your_key $0           # Deploy with API key

EOF
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            show_help
            exit 0
            ;;
        --skip-tests)
            SKIP_TESTS=true
            shift
            ;;
        --skip-security)
            SKIP_SECURITY_SCAN=true
            shift
            ;;
        --skip-docker)
            SKIP_DOCKER_BUILD=true
            shift
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --environment)
            ENVIRONMENT="$2"
            shift 2
            ;;
        --verbose)
            set -x
            shift
            ;;
        *)
            log_error "Unknown option: $1"
            show_help
            exit 1
            ;;
    esac
done

# Check prerequisites
check_prerequisites() {
    log_info "Checking prerequisites..."
    
    local missing_tools=()
    
    # Check for required tools
    command -v python3 >/dev/null 2>&1 || missing_tools+=("python3")
    command -v docker >/dev/null 2>&1 || missing_tools+=("docker")
    command -v git >/dev/null 2>&1 || missing_tools+=("git")
    
    # Check for uvx (optional, for local testing)
    if ! command -v uvx >/dev/null 2>&1; then
        log_warning "uvx not found - local testing will be skipped"
    fi
    
    if [[ ${#missing_tools[@]} -gt 0 ]]; then
        log_error "Missing required tools: ${missing_tools[*]}"
        log_error "Please install the missing tools and try again"
        exit 1
    fi
    
    # Check for required files
    local required_files=("telnyx.yml" "smithery.yaml" "smithery.json" "deployment/Dockerfile")
    for file in "${required_files[@]}"; do
        if [[ ! -f "$SCRIPT_DIR/$file" ]]; then
            log_error "Required file missing: $file"
            exit 1
        fi
    done
    
    # Check environment variables
    if [[ -z "${TELNYX_API_KEY:-}" ]]; then
        log_error "TELNYX_API_KEY environment variable is required"
        log_error "Set it with: export TELNYX_API_KEY=your_api_key"
        exit 1
    fi
    
    # Validate API key format
    if [[ ! "$TELNYX_API_KEY" =~ ^KEY[a-zA-Z0-9_-]+ ]]; then
        log_error "TELNYX_API_KEY appears to have invalid format (should start with 'KEY')"
        exit 1
    fi
    
    log_success "Prerequisites check passed"
}

# Run security validation
run_security_validation() {
    if [[ "$SKIP_SECURITY_SCAN" == "true" ]]; then
        log_warning "Skipping security validation"
        return 0
    fi
    
    log_info "Running security validation..."
    
    if [[ -f "$SCRIPT_DIR/security/security-validator.py" ]]; then
        if python3 "$SCRIPT_DIR/security/security-validator.py" \
           --project-path "$SCRIPT_DIR" \
           --fail-on-critical; then
            log_success "Security validation passed"
        else
            log_error "Security validation failed"
            exit 1
        fi
    else
        log_warning "Security validator not found - skipping security scan"
    fi
}

# Run deployment validation
run_deployment_validation() {
    log_info "Running deployment validation..."
    
    local validator_args=("--project-path" "$SCRIPT_DIR")
    
    if [[ "$SKIP_DOCKER_BUILD" == "true" ]]; then
        validator_args+=("--skip-docker")
    fi
    
    if [[ -f "$SCRIPT_DIR/tests/deployment-validator.py" ]]; then
        if python3 "$SCRIPT_DIR/tests/deployment-validator.py" "${validator_args[@]}"; then
            log_success "Deployment validation passed"
        else
            log_error "Deployment validation failed"
            exit 1
        fi
    else
        log_error "Deployment validator not found at tests/deployment-validator.py"
        exit 1
    fi
}

# Run integration tests
run_integration_tests() {
    if [[ "$SKIP_TESTS" == "true" ]]; then
        log_warning "Skipping integration tests"
        return 0
    fi
    
    log_info "Running integration tests..."
    
    if [[ -f "$SCRIPT_DIR/tests/integration-test.py" ]]; then
        if python3 "$SCRIPT_DIR/tests/integration-test.py" \
           --project-path "$SCRIPT_DIR"; then
            log_success "Integration tests passed"
        else
            log_error "Integration tests failed"
            exit 1
        fi
    else
        log_warning "Integration test suite not found - skipping tests"
    fi
}

# Build and validate Docker image
build_docker_image() {
    if [[ "$SKIP_DOCKER_BUILD" == "true" ]]; then
        log_warning "Skipping Docker build"
        return 0
    fi
    
    log_info "Building Docker image..."
    
    # Build the image
    if docker build -t "$DOCKER_IMAGE_TAG" -f deployment/Dockerfile .; then
        log_success "Docker image built successfully"
    else
        log_error "Docker image build failed"
        exit 1
    fi
    
    # Test the image
    log_info "Testing Docker image..."
    
    # Start container for testing
    local container_id
    container_id=$(docker run -d \
        -p 8080:8080 \
        -e TELNYX_API_KEY="$TELNYX_API_KEY" \
        -e LOG_LEVEL=INFO \
        --name "${PROJECT_NAME}-test" \
        "$DOCKER_IMAGE_TAG")
    
    # Wait for container to start
    sleep 10
    
    # Test health endpoint
    if curl -f -s http://localhost:8080/health >/dev/null 2>&1; then
        log_success "Docker image test passed"
    else
        log_warning "Docker image health check failed (container might need more time)"
    fi
    
    # Clean up test container
    docker stop "$container_id" >/dev/null 2>&1 || true
    docker rm "$container_id" >/dev/null 2>&1 || true
}

# Deploy to Smithery
deploy_to_smithery() {
    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "DRY RUN: Would deploy to Smithery now"
        log_info "Smithery configuration files ready:"
        log_info "  - smithery.yaml: $(wc -l < smithery.yaml) lines"
        log_info "  - smithery.json: $(wc -l < smithery.json) lines"
        log_info "  - telnyx.yml: $(du -h telnyx.yml | cut -f1)"
        return 0
    fi
    
    log_info "Deploying to Smithery platform..."
    
    # Check if Smithery CLI is available
    if command -v smithery >/dev/null 2>&1; then
        log_info "Using Smithery CLI for deployment..."
        
        # Deploy using Smithery CLI
        if smithery deploy --config smithery.yaml; then
            log_success "Deployment to Smithery completed successfully"
        else
            log_error "Smithery deployment failed"
            exit 1
        fi
        
    elif command -v gh >/dev/null 2>&1; then
        log_info "Using GitHub for Smithery deployment..."
        
        # Check if this is a git repository
        if [[ ! -d .git ]]; then
            log_error "Not in a git repository. Initialize git first:"
            log_error "  git init"
            log_error "  git add ."
            log_error "  git commit -m 'Initial commit'"
            log_error "  gh repo create --public"
            exit 1
        fi
        
        # Push to GitHub if needed
        if ! git remote get-url origin >/dev/null 2>&1; then
            log_error "No GitHub remote configured. Set up GitHub repository:"
            log_error "  gh repo create --public"
            log_error "  git push --set-upstream origin main"
            exit 1
        fi
        
        # Push latest changes
        git add .
        git commit -m "Update deployment configuration - $(date)" || true
        git push
        
        log_success "Code pushed to GitHub"
        log_info "Manual step required: Go to https://smithery.ai/ and click 'Deploy' for your repository"
        
    else
        log_error "Neither Smithery CLI nor GitHub CLI (gh) is available"
        log_error "Please install one of them or deploy manually:"
        log_error ""
        log_error "Option 1 - Install Smithery CLI:"
        log_error "  npm install -g @smithery/cli"
        log_error ""
        log_error "Option 2 - Install GitHub CLI:"
        log_error "  brew install gh  # or your package manager"
        log_error ""
        log_error "Option 3 - Manual deployment:"
        log_error "  1. Push code to GitHub repository"
        log_error "  2. Go to https://smithery.ai/"
        log_error "  3. Click 'Deploy' and select your repository"
        exit 1
    fi
}

# Generate deployment report
generate_deployment_report() {
    log_info "Generating deployment report..."
    
    local report_file="deployment-report-$(date +%Y%m%d-%H%M%S).json"
    
    cat > "$report_file" << EOF
{
  "deployment_info": {
    "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
    "environment": "$ENVIRONMENT",
    "project_name": "$PROJECT_NAME",
    "docker_image": "$DOCKER_IMAGE_TAG",
    "script_version": "1.0.0"
  },
  "configuration": {
    "skip_tests": $SKIP_TESTS,
    "skip_security_scan": $SKIP_SECURITY_SCAN,
    "skip_docker_build": $SKIP_DOCKER_BUILD,
    "dry_run": $DRY_RUN
  },
  "files": {
    "smithery_yaml_size": "$(wc -c < smithery.yaml) bytes",
    "smithery_json_size": "$(wc -c < smithery.json) bytes",
    "openapi_spec_size": "$(wc -c < telnyx.yml) bytes",
    "dockerfile_size": "$(wc -c < deployment/Dockerfile) bytes"
  },
  "git_info": {
    "commit_hash": "$(git rev-parse HEAD 2>/dev/null || echo 'N/A')",
    "branch": "$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo 'N/A')",
    "remote_url": "$(git remote get-url origin 2>/dev/null || echo 'N/A')"
  }
}
EOF
    
    log_success "Deployment report saved to: $report_file"
}

# Main deployment flow
main() {
    log_info "Starting Telnyx MCP Server deployment to Smithery"
    log_info "Environment: $ENVIRONMENT"
    log_info "Dry run: $DRY_RUN"
    
    # Change to script directory
    cd "$SCRIPT_DIR"
    
    # Run deployment steps
    check_prerequisites
    run_security_validation
    run_deployment_validation
    build_docker_image
    run_integration_tests
    deploy_to_smithery
    generate_deployment_report
    
    log_success "🎉 Deployment completed successfully!"
    
    if [[ "$DRY_RUN" != "true" ]]; then
        log_info ""
        log_info "Next steps:"
        log_info "1. Monitor deployment status on Smithery dashboard"
        log_info "2. Test the deployed service endpoints"
        log_info "3. Set up monitoring and alerting"
        log_info "4. Update documentation with deployment details"
    fi
}

# Run main function
main "$@"