package s3compat

import (
	"context"
	"strings"
	"testing"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/service/s3"
	"github.com/ekkuleivonen/relic/packages/storage"
)

func TestBucketConfigFromStorage(t *testing.T) {
	bucket := storage.Bucket{
		EndpointURL: "https://example-r2.r2.cloudflarestorage.com",
		Region:      "auto",
		BucketName:  "photos",
		Prefix:      "imports/",
		UpstreamConfig: storage.BucketUpstreamConfig{
			"s3": map[string]any{
				"force_path_style": true,
				"signing_region":   "us-east-1",
				"use_legacy_list":  true,
			},
		},
	}

	config, err := BucketConfigFromStorage(bucket)
	if err != nil {
		t.Fatalf("BucketConfigFromStorage returned error: %v", err)
	}

	if config.EndpointURL != bucket.EndpointURL {
		t.Fatalf("EndpointURL = %q, want %q", config.EndpointURL, bucket.EndpointURL)
	}
	if config.Region != "auto" {
		t.Fatalf("Region = %q, want auto", config.Region)
	}
	if config.SigningRegion != "us-east-1" {
		t.Fatalf("SigningRegion = %q, want us-east-1", config.SigningRegion)
	}
	if !config.ForcePathStyle {
		t.Fatal("ForcePathStyle = false, want true")
	}
	if !config.UseLegacyList {
		t.Fatal("UseLegacyList = false, want true")
	}
}

func TestBucketConfigFromStorageDefaultsSigningRegion(t *testing.T) {
	config, err := BucketConfigFromStorage(storage.Bucket{
		EndpointURL: "https://s3.amazonaws.com",
		Region:      "eu-west-1",
		BucketName:  "photos",
	})
	if err != nil {
		t.Fatalf("BucketConfigFromStorage returned error: %v", err)
	}

	if config.SigningRegion != "eu-west-1" {
		t.Fatalf("SigningRegion = %q, want eu-west-1", config.SigningRegion)
	}
}

func TestClientFactoryNewClientBuildsSDKClient(t *testing.T) {
	var capturedConfig aws.Config
	var capturedOptions s3.Options
	factory := ClientFactory{
		NewS3API: func(config aws.Config, options ...func(*s3.Options)) S3API {
			capturedConfig = config
			for _, option := range options {
				option(&capturedOptions)
			}
			return &fakeS3API{}
		},
	}

	client, err := factory.NewClient(context.Background(), BucketConfig{
		EndpointURL:    "https://s3.example.test",
		Region:         "auto",
		SigningRegion:  "us-east-1",
		BucketName:     "photos",
		ForcePathStyle: true,
		UseLegacyList:  true,
	}, Credentials{
		AccessKeyID:     "access-key",
		SecretAccessKey: "secret-key",
		SessionToken:    "session-token",
	})
	if err != nil {
		t.Fatalf("NewClient returned error: %v", err)
	}

	if client == nil {
		t.Fatal("NewClient returned nil client")
	}
	if capturedConfig.Region != "us-east-1" {
		t.Fatalf("captured region = %q, want us-east-1", capturedConfig.Region)
	}
	credentials, err := capturedConfig.Credentials.Retrieve(context.Background())
	if err != nil {
		t.Fatalf("Retrieve credentials returned error: %v", err)
	}
	if credentials.AccessKeyID != "access-key" {
		t.Fatalf("AccessKeyID = %q, want access-key", credentials.AccessKeyID)
	}
	if credentials.SecretAccessKey != "secret-key" {
		t.Fatalf("SecretAccessKey = %q, want secret-key", credentials.SecretAccessKey)
	}
	if credentials.SessionToken != "session-token" {
		t.Fatalf("SessionToken = %q, want session-token", credentials.SessionToken)
	}
	if capturedOptions.BaseEndpoint == nil || *capturedOptions.BaseEndpoint != "https://s3.example.test" {
		t.Fatalf("BaseEndpoint = %#v, want https://s3.example.test", capturedOptions.BaseEndpoint)
	}
	if !capturedOptions.UsePathStyle {
		t.Fatal("UsePathStyle = false, want true")
	}
}

func TestClientFactoryNewClientRejectsInvalidConfig(t *testing.T) {
	factory := ClientFactory{NewS3API: func(config aws.Config, options ...func(*s3.Options)) S3API {
		return &fakeS3API{}
	}}

	_, err := factory.NewClient(context.Background(), BucketConfig{}, Credentials{
		AccessKeyID:     "access-key",
		SecretAccessKey: "secret-key",
	})
	if err == nil {
		t.Fatal("NewClient returned nil error, want config validation error")
	}
	if !strings.Contains(err.Error(), "bucket name is required") {
		t.Fatalf("error = %q, want bucket name validation", err.Error())
	}
}

func TestClientFactoryNewClientRejectsInvalidCredentials(t *testing.T) {
	factory := ClientFactory{NewS3API: func(config aws.Config, options ...func(*s3.Options)) S3API {
		return &fakeS3API{}
	}}

	_, err := factory.NewClient(context.Background(), BucketConfig{
		EndpointURL: "https://s3.example.test",
		Region:      "us-east-1",
		BucketName:  "photos",
	}, Credentials{})
	if err == nil {
		t.Fatal("NewClient returned nil error, want credentials validation error")
	}
	if !strings.Contains(err.Error(), "access_key_id is required") {
		t.Fatalf("error = %q, want access_key_id validation", err.Error())
	}
}
