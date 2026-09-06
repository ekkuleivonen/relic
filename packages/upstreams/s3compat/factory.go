package s3compat

import (
	"context"
	"fmt"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/service/s3"
	"github.com/aws/smithy-go/middleware"
	"github.com/elei-io/pithosys/packages/storage"
)

type BucketConfig struct {
	EndpointURL    string
	Region         string
	SigningRegion  string
	BucketName     string
	Prefix         string
	ForcePathStyle bool
	UseLegacyList  bool
}

type ClientFactory struct {
	NewS3API func(aws.Config, ...func(*s3.Options)) S3API
}

type ObjectClientFactory interface {
	NewClient(context.Context, BucketConfig, Credentials) (ObjectClient, error)
}

func (f ClientFactory) NewClient(ctx context.Context, config BucketConfig, credentials Credentials) (ObjectClient, error) {
	if err := config.Validate(); err != nil {
		return nil, err
	}
	if err := credentials.Validate(); err != nil {
		return nil, err
	}

	newS3API := f.NewS3API
	if newS3API == nil {
		newS3API = func(config aws.Config, options ...func(*s3.Options)) S3API {
			return s3.NewFromConfig(config, options...)
		}
	}

	api := newS3API(aws.Config{
		Region:      config.resolvedSigningRegion(),
		Credentials: staticCredentialsProvider{credentials: credentials},
	}, func(options *s3.Options) {
		options.BaseEndpoint = aws.String(config.EndpointURL)
		options.UsePathStyle = config.ForcePathStyle
		options.APIOptions = append(options.APIOptions, func(stack *middleware.Stack) error {
			return AttachCaptureResponseHeaders(stack)
		})
	})

	return NewSDKClient(SDKClientOptions{
		API:           api,
		UseLegacyList: config.UseLegacyList,
	})
}

func BucketConfigFromStorage(bucket storage.Bucket) (BucketConfig, error) {
	config := BucketConfig{
		EndpointURL:   bucket.EndpointURL,
		Region:        bucket.Region,
		SigningRegion: bucket.Region,
		BucketName:    bucket.BucketName,
		Prefix:        bucket.Prefix,
	}

	s3Config, err := mapValue(bucket.UpstreamConfig, "s3")
	if err != nil {
		return BucketConfig{}, err
	}
	if s3Config == nil {
		return config, nil
	}

	config.ForcePathStyle, err = boolConfig(s3Config, "force_path_style")
	if err != nil {
		return BucketConfig{}, err
	}
	config.UseLegacyList, err = boolConfig(s3Config, "use_legacy_list")
	if err != nil {
		return BucketConfig{}, err
	}
	signingRegion, err := stringConfig(s3Config, "signing_region")
	if err != nil {
		return BucketConfig{}, err
	}
	if signingRegion != "" {
		config.SigningRegion = signingRegion
	}

	return config, nil
}

func (c BucketConfig) Validate() error {
	if c.BucketName == "" {
		return fmt.Errorf("bucket name is required")
	}
	if c.EndpointURL == "" {
		return fmt.Errorf("endpoint URL is required")
	}
	if c.resolvedSigningRegion() == "" {
		return fmt.Errorf("signing region is required")
	}

	return nil
}

func (c BucketConfig) resolvedSigningRegion() string {
	if c.SigningRegion != "" {
		return c.SigningRegion
	}

	return c.Region
}

func (c Credentials) Validate() error {
	if c.AccessKeyID == "" {
		return fmt.Errorf("access_key_id is required")
	}
	if c.SecretAccessKey == "" {
		return fmt.Errorf("secret_access_key is required")
	}

	return nil
}

type staticCredentialsProvider struct {
	credentials Credentials
}

func (p staticCredentialsProvider) Retrieve(context.Context) (aws.Credentials, error) {
	return aws.Credentials{
		AccessKeyID:     p.credentials.AccessKeyID,
		SecretAccessKey: p.credentials.SecretAccessKey,
		SessionToken:    p.credentials.SessionToken,
		Source:          "pithosys-s3compat-static",
	}, nil
}

func mapValue(config storage.BucketUpstreamConfig, key string) (map[string]any, error) {
	value, ok := config[key]
	if !ok || value == nil {
		return nil, nil
	}
	typed, ok := value.(map[string]any)
	if !ok {
		return nil, fmt.Errorf("upstream_config.%s must be an object", key)
	}

	return typed, nil
}

func boolConfig(config map[string]any, key string) (bool, error) {
	value, ok := config[key]
	if !ok || value == nil {
		return false, nil
	}
	typed, ok := value.(bool)
	if !ok {
		return false, fmt.Errorf("upstream_config.s3.%s must be a boolean", key)
	}

	return typed, nil
}

func stringConfig(config map[string]any, key string) (string, error) {
	value, ok := config[key]
	if !ok || value == nil {
		return "", nil
	}
	typed, ok := value.(string)
	if !ok {
		return "", fmt.Errorf("upstream_config.s3.%s must be a string", key)
	}

	return typed, nil
}
