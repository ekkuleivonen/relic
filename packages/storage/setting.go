package storage

import (
	"fmt"
	"strconv"
	"time"
)

type SettingType string

const (
	SettingTypeDuration SettingType = "duration"
	SettingTypeBool     SettingType = "bool"
)

const (
	SettingWorkerRunnerPollInterval                  = "WORKER_RUNNER_POLL_INTERVAL"
	SettingWorkerRunnerRetryDelay                    = "WORKER_RUNNER_RETRY_DELAY"
	SettingWorkerScanSchedulerInterval               = "WORKER_SCAN_SCHEDULER_INTERVAL"
	SettingWorkerScanStagger                         = "WORKER_SCAN_STAGGER"
	SettingWorkerDuplicateDetectionSchedulerInterval = "WORKER_DUPLICATE_DETECTION_SCHEDULER_INTERVAL"
	SettingWorkerUpstreamProcessorInterval           = "WORKER_UPSTREAM_PROCESSOR_INTERVAL"
	SettingWorkerConfigRefetchInterval               = "WORKER_CONFIG_REFETCH_INTERVAL"
	SettingScanBucketEnabled                         = "SCAN_BUCKET_ENABLED"
	SettingScanBucketInterval                        = "SCAN_BUCKET_INTERVAL"
	SettingDuplicateDetectionEnabled                 = "DUPLICATE_DETECTION_ENABLED"
	SettingDuplicateDetectionInterval                = "DUPLICATE_DETECTION_INTERVAL"
)

type SettingDefinition struct {
	Key      string
	Default  string
	Type     SettingType
	Encrypted bool
}

type Setting struct {
	Key       string
	Value     string
	Encrypted bool
	UpdatedAt time.Time
	UpdatedBy *string
}

var SettingDefinitions = []SettingDefinition{
	{Key: SettingWorkerRunnerPollInterval, Default: "2s", Type: SettingTypeDuration},
	{Key: SettingWorkerRunnerRetryDelay, Default: "30s", Type: SettingTypeDuration},
	{Key: SettingWorkerScanSchedulerInterval, Default: "2s", Type: SettingTypeDuration},
	{Key: SettingWorkerScanStagger, Default: "30s", Type: SettingTypeDuration},
	{Key: SettingWorkerDuplicateDetectionSchedulerInterval, Default: "2s", Type: SettingTypeDuration},
	{Key: SettingWorkerUpstreamProcessorInterval, Default: "2s", Type: SettingTypeDuration},
	{Key: SettingWorkerConfigRefetchInterval, Default: "5m", Type: SettingTypeDuration},
	{Key: SettingScanBucketEnabled, Default: "true", Type: SettingTypeBool},
	{Key: SettingScanBucketInterval, Default: "24h", Type: SettingTypeDuration},
	{Key: SettingDuplicateDetectionEnabled, Default: "false", Type: SettingTypeBool},
	{Key: SettingDuplicateDetectionInterval, Default: "24h", Type: SettingTypeDuration},
}

func SettingDefinitionByKey(key string) (SettingDefinition, bool) {
	for _, definition := range SettingDefinitions {
		if definition.Key == key {
			return definition, true
		}
	}

	return SettingDefinition{}, false
}

func ValidateSettingValue(definition SettingDefinition, value string) error {
	switch definition.Type {
	case SettingTypeDuration:
		parsed, err := time.ParseDuration(value)
		if err != nil {
			return fmt.Errorf("invalid duration for %s: %w", definition.Key, err)
		}
		if parsed <= 0 {
			return fmt.Errorf("invalid duration for %s: must be positive", definition.Key)
		}
	case SettingTypeBool:
		if _, err := strconv.ParseBool(value); err != nil {
			return fmt.Errorf("invalid bool for %s: %w", definition.Key, err)
		}
	default:
		return fmt.Errorf("unsupported setting type for %s", definition.Key)
	}

	return nil
}

func ParseSettingDuration(key, value string) (time.Duration, error) {
	definition, ok := SettingDefinitionByKey(key)
	if !ok {
		return 0, fmt.Errorf("unknown setting %q", key)
	}

	if err := ValidateSettingValue(definition, value); err != nil {
		return 0, err
	}

	return time.ParseDuration(value)
}

func ParseSettingBool(key, value string) (bool, error) {
	definition, ok := SettingDefinitionByKey(key)
	if !ok {
		return false, fmt.Errorf("unknown setting %q", key)
	}

	if err := ValidateSettingValue(definition, value); err != nil {
		return false, err
	}

	return strconv.ParseBool(value)
}
