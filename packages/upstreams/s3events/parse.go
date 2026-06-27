package s3events

import (
	"encoding/base64"
	"encoding/json"
	"fmt"
	"net/url"
	"strconv"
	"strings"
	"time"

	"github.com/ekkuleivonen/relic/packages/upstreams/s3compat"
)

func Parse(body []byte) ([]NormalizedEvent, error) {
	var envelope map[string]json.RawMessage
	if err := json.Unmarshal(body, &envelope); err != nil {
		return nil, fmt.Errorf("parse notification: %w", err)
	}

	if bodyRaw, ok := envelope["body"]; ok && !hasKey(envelope, "Records") && !hasKey(envelope, "records") {
		trimmed := strings.TrimSpace(string(bodyRaw))
		if trimmed != "" && strings.HasPrefix(trimmed, "{") {
			return Parse([]byte(trimmed))
		}
	}

	switch {
	case hasKey(envelope, "Type"):
		return parseSNSEnvelope(body)
	case hasKey(envelope, "detail-type"):
		return parseEventBridge(body)
	case hasKey(envelope, "events"):
		return parseB2(body)
	case hasKey(envelope, "message"):
		return parseGCPPubSubPush(body)
	case hasKey(envelope, "action") && hasKey(envelope, "bucket"):
		return parseR2(body)
	case hasKey(envelope, "Records"):
		return parseS3Records(body)
	case hasKey(envelope, "records"):
		return parseLegacyRustFS(body)
	default:
		return nil, fmt.Errorf("parse notification: unsupported format")
	}
}

func parseSNSEnvelope(body []byte) ([]NormalizedEvent, error) {
	var message struct {
		Type    string `json:"Type"`
		Message string `json:"Message"`
	}
	if err := json.Unmarshal(body, &message); err != nil {
		return nil, fmt.Errorf("parse sns notification: %w", err)
	}

	switch message.Type {
	case "Notification":
		if strings.TrimSpace(message.Message) == "" {
			return nil, fmt.Errorf("parse sns notification: empty message")
		}
		return Parse([]byte(message.Message))
	case "SubscriptionConfirmation", "UnsubscribeConfirmation":
		return nil, nil
	default:
		return nil, fmt.Errorf("parse sns notification: unsupported type %q", message.Type)
	}
}

func parseEventBridge(body []byte) ([]NormalizedEvent, error) {
	var payload struct {
		DetailType string `json:"detail-type"`
		Time       string `json:"time"`
		Region     string `json:"region"`
		Detail     struct {
			Bucket struct {
				Name string `json:"name"`
			} `json:"bucket"`
			Object struct {
				Key       string `json:"key"`
				Size      int64  `json:"size"`
				ETag      string `json:"etag"`
				VersionID string `json:"version-id"`
			} `json:"object"`
		} `json:"detail"`
	}
	if err := json.Unmarshal(body, &payload); err != nil {
		return nil, fmt.Errorf("parse eventbridge notification: %w", err)
	}

	eventTime, err := parseTime(payload.Time)
	if err != nil {
		return nil, fmt.Errorf("parse eventbridge notification: %w", err)
	}

	event := NormalizedEvent{
		Upstream:    s3compat.UpstreamAWS,
		Action:      actionFromEventName(payload.DetailType),
		EventName:   payload.DetailType,
		EventSource: "aws:eventbridge",
		BucketName:  payload.Detail.Bucket.Name,
		Region:      payload.Region,
		Key:         payload.Detail.Object.Key,
		ETag:        payload.Detail.Object.ETag,
		Size:        payload.Detail.Object.Size,
		EventTime:   eventTime,
		VersionID:   payload.Detail.Object.VersionID,
	}
	if event.Key == "" || event.Action == EventActionIgnore {
		return nil, nil
	}

	return []NormalizedEvent{event}, nil
}

func parseB2(body []byte) ([]NormalizedEvent, error) {
	var payload struct {
		Events []struct {
			EventID        string `json:"eventId"`
			EventTimestamp int64  `json:"eventTimestamp"`
			EventType      string `json:"eventType"`
			BucketName     string `json:"bucketName"`
			ObjectName     string `json:"objectName"`
			ObjectSize     int64  `json:"objectSize"`
		} `json:"events"`
	}
	if err := json.Unmarshal(body, &payload); err != nil {
		return nil, fmt.Errorf("parse b2 notification: %w", err)
	}

	events := make([]NormalizedEvent, 0, len(payload.Events))
	for _, item := range payload.Events {
		action := actionFromEventName(item.EventType)
		if item.ObjectName == "" || action == EventActionIgnore {
			continue
		}

		events = append(events, NormalizedEvent{
			Upstream:   s3compat.UpstreamB2,
			Action:     action,
			EventName:  item.EventType,
			BucketName: item.BucketName,
			Key:        item.ObjectName,
			Size:       item.ObjectSize,
			EventTime:  time.UnixMilli(item.EventTimestamp).UTC(),
			EventID:    item.EventID,
		})
	}

	return events, nil
}

func parseGCPPubSubPush(body []byte) ([]NormalizedEvent, error) {
	var payload struct {
		Message struct {
			Attributes map[string]string `json:"attributes"`
			Data       string            `json:"data"`
		} `json:"message"`
	}
	if err := json.Unmarshal(body, &payload); err != nil {
		return nil, fmt.Errorf("parse gcp pubsub notification: %w", err)
	}

	attributes := payload.Message.Attributes
	eventName := attributes["eventType"]
	action := actionFromEventName(eventName)
	if action == EventActionIgnore {
		return nil, nil
	}

	eventTime, err := parseTime(attributes["eventTime"])
	if err != nil {
		return nil, fmt.Errorf("parse gcp pubsub notification: %w", err)
	}

	event := NormalizedEvent{
		Upstream:   s3compat.UpstreamGCP,
		Action:     action,
		EventName:  eventName,
		BucketName: attributes["bucketId"],
		Key:        attributes["objectId"],
		EventTime:  eventTime,
		VersionID:  attributes["objectGeneration"],
	}

	if encoded := strings.TrimSpace(payload.Message.Data); encoded != "" {
		decoded, err := base64.StdEncoding.DecodeString(encoded)
		if err != nil {
			return nil, fmt.Errorf("parse gcp pubsub notification: decode data: %w", err)
		}

		var object struct {
			Size    string `json:"size"`
			MD5Hash string `json:"md5Hash"`
		}
		if err := json.Unmarshal(decoded, &object); err != nil {
			return nil, fmt.Errorf("parse gcp pubsub notification: decode object payload: %w", err)
		}
		if event.Size == 0 && object.Size != "" {
			size, err := strconv.ParseInt(object.Size, 10, 64)
			if err != nil {
				return nil, fmt.Errorf("parse gcp pubsub notification: parse object size: %w", err)
			}
			event.Size = size
		}
		if event.ETag == "" {
			event.ETag = object.MD5Hash
		}
	}

	if event.Key == "" {
		return nil, nil
	}

	return []NormalizedEvent{event}, nil
}

func parseR2(body []byte) ([]NormalizedEvent, error) {
	var payload struct {
		Action    string `json:"action"`
		Bucket    string `json:"bucket"`
		EventTime string `json:"eventTime"`
		Object    struct {
			Key  string `json:"key"`
			Size int64  `json:"size"`
			ETag string `json:"eTag"`
		} `json:"object"`
	}
	if err := json.Unmarshal(body, &payload); err != nil {
		return nil, fmt.Errorf("parse r2 notification: %w", err)
	}

	action := actionFromEventName(payload.Action)
	if payload.Object.Key == "" || action == EventActionIgnore {
		return nil, nil
	}

	eventTime, err := parseTime(payload.EventTime)
	if err != nil {
		return nil, fmt.Errorf("parse r2 notification: %w", err)
	}

	return []NormalizedEvent{{
		Upstream:   s3compat.UpstreamR2,
		Action:     action,
		EventName:  payload.Action,
		BucketName: payload.Bucket,
		Key:        payload.Object.Key,
		ETag:       payload.Object.ETag,
		Size:       payload.Object.Size,
		EventTime:  eventTime,
	}}, nil
}

func parseS3Records(body []byte) ([]NormalizedEvent, error) {
	var payload struct {
		Records []s3Record `json:"Records"`
	}
	if err := json.Unmarshal(body, &payload); err != nil {
		return nil, fmt.Errorf("parse s3 records notification: %w", err)
	}

	return normalizedEventsFromS3Records(payload.Records)
}

func parseLegacyRustFS(body []byte) ([]NormalizedEvent, error) {
	var payload struct {
		Records []s3Record `json:"records"`
	}
	if err := json.Unmarshal(body, &payload); err != nil {
		return nil, fmt.Errorf("parse legacy rustfs notification: %w", err)
	}

	events, err := normalizedEventsFromS3Records(payload.Records)
	if err != nil {
		return nil, err
	}
	for i := range events {
		if events[i].Upstream == s3compat.UpstreamAWS {
			events[i].Upstream = s3compat.UpstreamRustFS
		}
	}

	return events, nil
}

type s3Record struct {
	EventSource      string            `json:"eventSource"`
	AWSRegion        string            `json:"awsRegion"`
	EventName        string            `json:"eventName"`
	EventTime        string            `json:"eventTime"`
	ResponseElements map[string]string `json:"responseElements"`
	S3               struct {
		Bucket struct {
			Name string `json:"name"`
			ARN  string `json:"arn"`
		} `json:"bucket"`
		Object struct {
			Key       string `json:"key"`
			Size      int64  `json:"size"`
			ETag      string `json:"eTag"`
			VersionID string `json:"versionId"`
		} `json:"object"`
	} `json:"s3"`
}

func normalizedEventsFromS3Records(records []s3Record) ([]NormalizedEvent, error) {
	events := make([]NormalizedEvent, 0, len(records))
	for _, record := range records {
		key, err := decodeObjectKey(record.S3.Object.Key)
		if err != nil {
			return nil, fmt.Errorf("parse s3 records notification: %w", err)
		}
		if key == "" {
			continue
		}

		action := actionFromEventName(record.EventName)
		if action == EventActionIgnore {
			continue
		}

		eventTime, err := parseTime(record.EventTime)
		if err != nil {
			return nil, fmt.Errorf("parse s3 records notification: %w", err)
		}

		events = append(events, NormalizedEvent{
			Upstream:     upstreamFromEventSource(record.EventSource),
			Action:         action,
			EventName:      record.EventName,
			EventSource:    record.EventSource,
			BucketName:     record.S3.Bucket.Name,
			BucketARN:      record.S3.Bucket.ARN,
			Region:         record.AWSRegion,
			DeploymentID:   deploymentIDFromResponseElements(record.ResponseElements),
			Key:            key,
			ETag:           record.S3.Object.ETag,
			Size:           record.S3.Object.Size,
			EventTime:      eventTime,
			VersionID:      record.S3.Object.VersionID,
		})
	}

	return events, nil
}

func deploymentIDFromResponseElements(responseElements map[string]string) string {
	if responseElements == nil {
		return ""
	}

	for key, value := range responseElements {
		if strings.EqualFold(key, "x-rustfs-deployment-id") {
			return strings.TrimSpace(value)
		}
	}

	return ""
}

func upstreamFromEventSource(eventSource string) s3compat.Upstream {
	switch strings.ToLower(eventSource) {
	case "aws:s3":
		return s3compat.UpstreamAWS
	case "rustfs:s3":
		return s3compat.UpstreamRustFS
	default:
		if strings.HasSuffix(strings.ToLower(eventSource), ":s3") {
			return s3compat.UpstreamAWS
		}

		return s3compat.UpstreamAWS
	}
}

func decodeObjectKey(raw string) (string, error) {
	if raw == "" {
		return "", nil
	}

	decoded, err := url.QueryUnescape(raw)
	if err != nil {
		return "", fmt.Errorf("decode object key %q: %w", raw, err)
	}

	return decoded, nil
}

func actionFromEventName(name string) EventAction {
	normalized := strings.ToLower(name)
	switch {
	case strings.Contains(normalized, "object created"),
		strings.Contains(normalized, "objectcreated"),
		strings.Contains(normalized, "putobject"),
		strings.Contains(normalized, "completemultipartupload"),
		strings.Contains(normalized, "copyobject"),
		strings.Contains(normalized, "object_finalize"),
		strings.Contains(normalized, "objectcreatedupload"),
		strings.Contains(normalized, "objectcreatedmultipartupload"):
		return EventActionImport
	case strings.Contains(normalized, "object deleted"),
		strings.Contains(normalized, "objectremoved"),
		strings.Contains(normalized, "deleteobject"),
		strings.Contains(normalized, "object_delete"),
		strings.Contains(normalized, "objectdeleted"):
		return EventActionRemove
	default:
		return EventActionIgnore
	}
}

func parseTime(value string) (time.Time, error) {
	if value == "" {
		return time.Time{}, fmt.Errorf("parse event time: value is empty")
	}

	layouts := []string{
		time.RFC3339Nano,
		time.RFC3339,
		"2006-01-02T15:04:05.000Z",
	}
	for _, layout := range layouts {
		if parsed, err := time.Parse(layout, value); err == nil {
			return parsed.UTC(), nil
		}
	}

	return time.Time{}, fmt.Errorf("parse event time %q", value)
}

func hasKey(envelope map[string]json.RawMessage, key string) bool {
	_, ok := envelope[key]
	return ok
}
