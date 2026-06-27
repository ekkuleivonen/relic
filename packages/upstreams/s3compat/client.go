package s3compat

import (
	"context"
	"fmt"
	"io"
	"net/http"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/service/s3"
)

type ObjectClient interface {
	ListObjects(context.Context, ListObjectsInput) (ObjectPage, error)
	HeadObject(context.Context, HeadObjectInput) (HeadObjectData, error)
	GetObject(context.Context, HeadObjectInput) (io.ReadCloser, error)
	GetObjectTagging(context.Context, HeadObjectInput) (map[string]string, error)
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
	GetObject(context.Context, *s3.GetObjectInput, ...func(*s3.Options)) (*s3.GetObjectOutput, error)
	GetObjectTagging(context.Context, *s3.GetObjectTaggingInput, ...func(*s3.Options)) (*s3.GetObjectTaggingOutput, error)
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

func (c *SDKClient) HeadObject(ctx context.Context, input HeadObjectInput) (HeadObjectData, error) {
	ctx, capture := WithHeaderCapture(ctx)
	output, err := c.api.HeadObject(ctx, &s3.HeadObjectInput{
		Bucket:    aws.String(input.Bucket),
		Key:       aws.String(input.Key),
		VersionId: optionalString(input.VersionID),
	})
	if err != nil {
		return HeadObjectData{}, err
	}

	headers := http.Header{}
	if capture != nil && capture.Headers != nil {
		headers = capture.Headers
	}

	return HeadObjectData{
		Output:          output,
		ResponseHeaders: headers,
	}, nil
}

func (c *SDKClient) GetObject(ctx context.Context, input HeadObjectInput) (io.ReadCloser, error) {
	output, err := c.api.GetObject(ctx, &s3.GetObjectInput{
		Bucket:    aws.String(input.Bucket),
		Key:       aws.String(input.Key),
		VersionId: optionalString(input.VersionID),
	})
	if err != nil {
		return nil, err
	}
	if output.Body == nil {
		return nil, fmt.Errorf("get object %q: empty body", input.Key)
	}

	return output.Body, nil
}

func (c *SDKClient) GetObjectTagging(ctx context.Context, input HeadObjectInput) (map[string]string, error) {
	output, err := c.api.GetObjectTagging(ctx, &s3.GetObjectTaggingInput{
		Bucket:    aws.String(input.Bucket),
		Key:       aws.String(input.Key),
		VersionId: optionalString(input.VersionID),
	})
	if err != nil {
		return nil, err
	}

	tags := map[string]string{}
	for _, tag := range output.TagSet {
		tags[aws.ToString(tag.Key)] = aws.ToString(tag.Value)
	}

	return tags, nil
}

func optionalString(value string) *string {
	if value == "" {
		return nil
	}

	return aws.String(value)
}
