package s3compat

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"io"
)

const hashReadBufferSize = 64 * 1024

func HashObject(ctx context.Context, client ObjectClient, bucketName string, input HeadObjectInput) (string, int64, error) {
	body, err := client.GetObject(ctx, HeadObjectInput{
		Bucket:    bucketName,
		Key:       input.Key,
		VersionID: input.VersionID,
	})
	if err != nil {
		return "", 0, fmt.Errorf("hash object %q: %w", input.Key, err)
	}
	defer body.Close()

	digest := sha256.New()
	var bytesRead int64
	buffer := make([]byte, hashReadBufferSize)
	for {
		if err := ctx.Err(); err != nil {
			return "", bytesRead, err
		}

		n, readErr := body.Read(buffer)
		if n > 0 {
			if _, err := digest.Write(buffer[:n]); err != nil {
				return "", bytesRead, fmt.Errorf("hash object %q: %w", input.Key, err)
			}
			bytesRead += int64(n)
		}
		if readErr == io.EOF {
			break
		}
		if readErr != nil {
			return "", bytesRead, fmt.Errorf("hash object %q: %w", input.Key, readErr)
		}
	}

	return hex.EncodeToString(digest.Sum(nil)), bytesRead, nil
}
