package upstreamprocessor

import "strings"

func KeyInBucketScope(bucketPrefix, key string) bool {
	if bucketPrefix == "" {
		return true
	}

	return strings.HasPrefix(key, bucketPrefix)
}
