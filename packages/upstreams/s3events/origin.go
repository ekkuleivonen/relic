package s3events

import (
	"net/url"
	"strings"

	"github.com/ekkuleivonen/relic/packages/upstreams/s3compat"
)

func (event NormalizedEvent) OriginKey() string {
	if deploymentID := strings.TrimSpace(event.DeploymentID); deploymentID != "" {
		return "deployment:" + deploymentID
	}

	region := strings.TrimSpace(event.Region)
	if region != "" && event.Upstream == s3compat.UpstreamAWS {
		return "aws:" + region
	}

	if region != "" {
		return "region:" + region
	}

	if eventSource := strings.TrimSpace(event.EventSource); eventSource != "" {
		return "eventsource:" + strings.ToLower(eventSource)
	}

	return ""
}

func OriginKeyFromEndpoint(endpointURL string, region string) string {
	endpoint := strings.ToLower(strings.TrimSpace(endpointURL))
	if isAWSEndpoint(endpoint) {
		region = strings.TrimSpace(region)
		if region == "" {
			region = "us-east-1"
		}

		return "aws:" + region
	}

	host := normalizeEndpointHost(endpointURL)
	if host == "" {
		return "unknown"
	}

	return "endpoint:" + host
}

func isAWSEndpoint(endpoint string) bool {
	if endpoint == "" {
		return true
	}

	return strings.Contains(endpoint, "amazonaws.com")
}

func normalizeEndpointHost(endpointURL string) string {
	parsed, err := url.Parse(strings.TrimSpace(endpointURL))
	if err != nil || parsed.Host == "" {
		return strings.Trim(strings.ToLower(strings.TrimPrefix(strings.TrimPrefix(endpointURL, "https://"), "http://")), "/")
	}

	return strings.ToLower(parsed.Host)
}
