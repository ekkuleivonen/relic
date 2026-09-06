// Command demo seeds only the isolated Compose environment with synthetic data.
package main

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/http/cookiejar"
	"os"
	"strings"
	"time"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/service/s3"
)

func main() {
	if err := run(); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}
func run() error {
	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Minute)
	defer cancel()
	endpoint := os.Getenv("S3_ENDPOINT")
	// This utility deliberately refuses arbitrary upstreams; it is not a production importer.
	if endpoint != "http://s3:7070" || os.Getenv("API_URL") != "http://api:8080" {
		return fmt.Errorf("demo requires the isolated Compose endpoints")
	}
	client := s3.NewFromConfig(aws.Config{Region: "us-east-1", Credentials: aws.CredentialsProviderFunc(func(context.Context) (aws.Credentials, error) {
		return aws.Credentials{AccessKeyID: os.Getenv("S3_ACCESS_KEY"), SecretAccessKey: os.Getenv("S3_SECRET_KEY")}, nil
	})}, func(o *s3.Options) { o.BaseEndpoint = aws.String(endpoint); o.UsePathStyle = true })
	bucket := "portfolio-demo"
	if _, err := client.HeadBucket(ctx, &s3.HeadBucketInput{Bucket: &bucket}); err != nil {
		if _, err = client.CreateBucket(ctx, &s3.CreateBucketInput{Bucket: &bucket}); err != nil {
			return fmt.Errorf("create synthetic bucket: %w", err)
		}
	}
	for i := 0; i < 128; i++ {
		team := []string{"research", "finance", "engineering", "design"}[i%4]
		key := fmt.Sprintf("%s/2026/report-%03d.json", team, i)
		body := fmt.Sprintf(`{"synthetic":true,"team":%q,"record":%d}`, team, i)
		_, err := client.PutObject(ctx, &s3.PutObjectInput{Bucket: &bucket, Key: &key, Body: strings.NewReader(body), ContentType: aws.String("application/json"), Metadata: map[string]string{"team": team, "dataset": "pithosys-demo"}})
		if err != nil {
			return fmt.Errorf("seed object: %w", err)
		}
	}
	jar, _ := cookiejar.New(nil)
	httpClient := &http.Client{Jar: jar, Timeout: 20 * time.Second}
	request := func(method, path string, payload any) (map[string]any, error) {
		b, err := json.Marshal(payload)
		if err != nil {
			return nil, err
		}
		req, err := http.NewRequestWithContext(ctx, method, os.Getenv("API_URL")+path, bytes.NewReader(b))
		if err != nil {
			return nil, err
		}
		req.Header.Set("Content-Type", "application/json")
		resp, err := httpClient.Do(req)
		if err != nil {
			return nil, err
		}
		defer resp.Body.Close()
		data, err := io.ReadAll(io.LimitReader(resp.Body, 2<<20))
		if err != nil {
			return nil, err
		}
		if resp.StatusCode >= 300 {
			return nil, fmt.Errorf("%s %s returned %d: %s", method, path, resp.StatusCode, data)
		}
		var result map[string]any
		if len(data) > 0 {
			err = json.Unmarshal(data, &result)
		}
		return result, err
	}
	if _, err := request("POST", "/api/auth/login", map[string]any{"email": "admin@example.com", "password": os.Getenv("SUPERUSER_PASSWORD")}); err != nil {
		return err
	}
	listing, err := request("GET", "/api/buckets", nil)
	if err != nil {
		return err
	}
	id := ""
	for _, raw := range listing["buckets"].([]any) {
		b := raw.(map[string]any)
		if b["bucket_name"] == bucket {
			id = b["id"].(string)
		}
	}
	started := time.Now()
	if id == "" {
		b, err := request("POST", "/api/buckets", map[string]any{"name": "Synthetic research archive", "upstream": "s3", "endpoint_url": endpoint, "region": "us-east-1", "bucket_name": bucket, "prefix": "", "upstream_config": map[string]any{"s3": map[string]any{"force_path_style": true}}, "credentials": map[string]string{"access_key_id": os.Getenv("S3_ACCESS_KEY"), "secret_access_key": os.Getenv("S3_SECRET_KEY")}})
		if err != nil {
			return err
		}
		id = b["id"].(string)
	} else {
		if _, err := request("POST", "/api/buckets/"+id+"/sync", nil); err != nil {
			return err
		}
	}
	var objects []any
	for {
		result, err := request("POST", "/api/search", map[string]string{"query": "FROM objects LIMIT 1000", "bucket_id": id})
		if err != nil {
			return err
		}
		objects, _ = result["objects"].([]any)
		runs, err := request("GET", "/api/job-runs?limit=100", nil)
		if err != nil {
			return err
		}
		active := false
		for _, raw := range runs["job_runs"].([]any) {
			r := raw.(map[string]any)
			if r["target_id"] != id {
				continue
			}
			switch r["state"] {
			case "pending", "running":
				active = true
			case "failed":
				return fmt.Errorf("demo sync failed; inspect worker logs")
			}
		}
		if len(objects) == 128 && !active {
			break
		}
		select {
		case <-ctx.Done():
			return fmt.Errorf("demo sync timed out with %d/128 objects", len(objects))
		case <-time.After(time.Second):
		}
	}
	elapsed := time.Since(started)
	objectID := objects[0].(map[string]any)["id"].(string)
	if _, err := request("PATCH", "/api/objects/"+objectID+"/attributes", map[string]any{"set": map[string]any{"user.reviewed": true}}); err != nil {
		return err
	}
	collections, err := request("GET", "/api/collections", nil)
	if err != nil {
		return err
	}
	found := false
	for _, raw := range collections["collections"].([]any) {
		if raw.(map[string]any)["name"] == "Reviewed demo objects" {
			found = true
		}
	}
	if !found {
		if _, err := request("POST", "/api/collections", map[string]string{"name": "Reviewed demo objects", "description": "Synthetic objects with a user review annotation.", "query": "FROM objects WHERE attr('user.reviewed') = true"}); err != nil {
			return err
		}
	}
	for i := 0; i < 10; i++ {
		start := time.Now()
		if _, err := request("POST", "/api/search", map[string]string{"query": "FROM objects LIMIT 100", "bucket_id": id}); err != nil {
			return err
		}
		fmt.Printf("search_sample_ms=%.2f\n", float64(time.Since(start).Microseconds())/1000)
	}
	fmt.Printf("PASS: 128 synthetic objects indexed; metadata update and saved collection verified. Sync elapsed: %s\n", elapsed.Round(time.Millisecond))
	return nil
}
