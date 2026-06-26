package s3compat

import (
	"context"
	"fmt"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/service/s3"
	"github.com/ekkuleivonen/relic/packages/storage"
)

type ObjectClient interface {
	ListObjects(context.Context, ListObjectsInput) (ObjectPage, error)
	HeadObject(context.Context, HeadObjectInput) (storage.ObjectAttributes, error)
}

type ListObjectsInput struct {
	Bucket            string
	Prefix            string
	ContinuationToken string
	Marker            string
}

type HeadObjectInput struct {
	Bucket    string
	Key       string
	VersionID string
}

type S3API interface {
	ListObjectsV2(context.Context, *s3.ListObjectsV2Input, ...func(*s3.Options)) (*s3.ListObjectsV2Output, error)
	ListObjects(context.Context, *s3.ListObjectsInput, ...func(*s3.Options)) (*s3.ListObjectsOutput, error)
	HeadObject(context.Context, *s3.HeadObjectInput, ...func(*s3.Options)) (*s3.HeadObjectOutput, error)
}

type SDKClient struct {
	api           S3API
	useLegacyList bool
}

type SDKClientOptions struct {
	API           S3API
	UseLegacyList bool
}

func NewSDKClient(options SDKClientOptions) (*SDKClient, error) {
	if options.API == nil {
		return nil, fmt.Errorf("create s3-compatible SDK client: S3 API is required")
	}

	return &SDKClient{
		api:           options.API,
		useLegacyList: options.UseLegacyList,
	}, nil
}

func (c *SDKClient) ListObjects(ctx context.Context, input ListObjectsInput) (ObjectPage, error) {
	if c.useLegacyList {
		output, err := c.api.ListObjects(ctx, &s3.ListObjectsInput{
			Bucket: aws.String(input.Bucket),
			Prefix: optionalString(input.Prefix),
			Marker: optionalString(input.Marker),
		})
		if err != nil {
			return ObjectPage{}, err
		}

		return ObjectPageFromListObjectsOutput(output), nil
	}

	output, err := c.api.ListObjectsV2(ctx, &s3.ListObjectsV2Input{
		Bucket:            aws.String(input.Bucket),
		Prefix:            optionalString(input.Prefix),
		ContinuationToken: optionalString(input.ContinuationToken),
	})
	if err != nil {
		return ObjectPage{}, err
	}

	return ObjectPageFromListObjectsV2Output(output), nil
}

func (c *SDKClient) HeadObject(ctx context.Context, input HeadObjectInput) (storage.ObjectAttributes, error) {
	output, err := c.api.HeadObject(ctx, &s3.HeadObjectInput{
		Bucket:    aws.String(input.Bucket),
		Key:       aws.String(input.Key),
		VersionId: optionalString(input.VersionID),
	})
	if err != nil {
		return nil, err
	}

	return AttributesFromHeadObjectOutput(output), nil
}

func optionalString(value string) *string {
	if value == "" {
		return nil
	}

	return aws.String(value)
}
