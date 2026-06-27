package storage

import "strings"

type BucketEventMatch struct {
	Platform         string
	Region           string
	Origin           string
	UpstreamBucketName string
	ObjectKey        string
}

func KeyInBucketPrefix(bucketPrefix, key string) bool {
	if bucketPrefix == "" {
		return true
	}

	return strings.HasPrefix(key, bucketPrefix)
}

func ResolveBucketForEvent(candidates []Bucket, match BucketEventMatch) (Bucket, string) {
	if len(candidates) == 0 {
		return Bucket{}, "bucket_not_found"
	}

	matched := make([]Bucket, 0, len(candidates))
	for _, bucket := range candidates {
		if bucket.BucketName != match.UpstreamBucketName {
			continue
		}
		if !bucketOriginMatches(bucket, match) {
			continue
		}
		if match.ObjectKey != "" && !KeyInBucketPrefix(bucket.Prefix, match.ObjectKey) {
			continue
		}
		matched = append(matched, bucket)
	}

	switch len(matched) {
	case 0:
		if len(candidates) == 1 &&
			candidates[0].BucketName == match.UpstreamBucketName &&
			match.ObjectKey != "" &&
			!KeyInBucketPrefix(candidates[0].Prefix, match.ObjectKey) {
			return Bucket{}, "out_of_scope"
		}

		return Bucket{}, "bucket_not_found"
	case 1:
		return matched[0], ""
	default:
		return Bucket{}, "ambiguous_bucket"
	}
}

func bucketOriginMatches(bucket Bucket, match BucketEventMatch) bool {
	if match.Origin == "" {
		return true
	}

	bucketOrigin := bucketOriginKey(bucket)
	if bucketOrigin == match.Origin {
		return true
	}

	if strings.HasPrefix(match.Origin, "aws:") && strings.HasPrefix(bucketOrigin, "aws:") {
		return bucketOrigin == match.Origin
	}

	if strings.HasPrefix(match.Origin, "deployment:") && !isAWSEndpointURL(bucket.EndpointURL) {
		return true
	}

	if strings.HasPrefix(match.Origin, "eventsource:") {
		return !isAWSEndpointURL(bucket.EndpointURL)
	}

	return false
}

func bucketOriginKey(bucket Bucket) string {
	endpoint := strings.ToLower(strings.TrimSpace(bucket.EndpointURL))
	if isAWSEndpointURL(endpoint) {
		region := strings.TrimSpace(bucket.Region)
		if region == "" {
			region = "us-east-1"
		}

		return "aws:" + region
	}

	host := normalizeEndpointHost(bucket.EndpointURL)
	if host == "" {
		return "unknown"
	}

	return "endpoint:" + host
}

func isAWSEndpointURL(endpoint string) bool {
	if endpoint == "" {
		return true
	}

	return strings.Contains(endpoint, "amazonaws.com")
}

func normalizeEndpointHost(endpointURL string) string {
	endpointURL = strings.TrimSpace(endpointURL)
	if endpointURL == "" {
		return ""
	}

	withoutScheme := strings.TrimPrefix(strings.TrimPrefix(endpointURL, "https://"), "http://")
	return strings.ToLower(strings.TrimSuffix(strings.Split(withoutScheme, "/")[0], "/"))
}
