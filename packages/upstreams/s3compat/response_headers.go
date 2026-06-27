package s3compat

import (
	"context"
	"net/http"

	"github.com/aws/smithy-go/middleware"
	smithyhttp "github.com/aws/smithy-go/transport/http"
)

type headerCaptureKey struct{}

type HeaderCapture struct {
	Headers http.Header
}

func WithHeaderCapture(ctx context.Context) (context.Context, *HeaderCapture) {
	capture := &HeaderCapture{}
	return context.WithValue(ctx, headerCaptureKey{}, capture), capture
}

func HeaderCaptureFromContext(ctx context.Context) *HeaderCapture {
	capture, _ := ctx.Value(headerCaptureKey{}).(*HeaderCapture)
	return capture
}

func AttachCaptureResponseHeaders(stack *middleware.Stack) error {
	return stack.Deserialize.Add(middleware.DeserializeMiddlewareFunc("CaptureResponseHeaders", func(ctx context.Context, in middleware.DeserializeInput, next middleware.DeserializeHandler) (middleware.DeserializeOutput, middleware.Metadata, error) {
		out, metadata, err := next.HandleDeserialize(ctx, in)
		if capture := HeaderCaptureFromContext(ctx); capture != nil {
			if response, ok := out.RawResponse.(*smithyhttp.Response); ok && response != nil {
				capture.Headers = response.Header.Clone()
			}
		}

		return out, metadata, err
	}), middleware.After)
}
