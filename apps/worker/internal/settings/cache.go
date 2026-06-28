package settings

import (
	"context"
	"strconv"
	"sync"
	"time"

	"github.com/ekkuleivonen/relic/packages/storage"
)

const defaultConfigRefetchInterval = 5 * time.Minute

type Reader interface {
	Duration(key string) time.Duration
	Bool(key string) bool
	Raw(key string) string
}

type Cache struct {
	mu     sync.RWMutex
	values map[string]string
}

func NewCache() *Cache {
	return &Cache{
		values: StaticFromRegistry(),
	}
}

func (c *Cache) Refresh(ctx context.Context, store *storage.SettingsStore) error {
	settings, err := store.List(ctx)
	if err != nil {
		return err
	}

	values := StaticFromRegistry()
	for _, setting := range settings {
		values[setting.Key] = setting.Value
	}

	c.mu.Lock()
	c.values = values
	c.mu.Unlock()

	return nil
}

func (c *Cache) Duration(key string) time.Duration {
	value := c.Raw(key)
	parsed, err := storage.ParseSettingDuration(key, value)
	if err != nil {
		return defaultDuration(key)
	}

	return parsed
}

func (c *Cache) Bool(key string) bool {
	value := c.Raw(key)
	parsed, err := storage.ParseSettingBool(key, value)
	if err != nil {
		return defaultBool(key)
	}

	return parsed
}

func (c *Cache) Raw(key string) string {
	c.mu.RLock()
	defer c.mu.RUnlock()

	if value, ok := c.values[key]; ok {
		return value
	}

	return defaultRaw(key)
}

func (c *Cache) RefetchInterval() time.Duration {
	interval := c.Duration(storage.SettingWorkerConfigRefetchInterval)
	if interval <= 0 {
		return defaultConfigRefetchInterval
	}

	return interval
}

type Static map[string]string

func StaticFromRegistry() map[string]string {
	values := make(map[string]string, len(storage.SettingDefinitions))
	for _, definition := range storage.SettingDefinitions {
		values[definition.Key] = definition.Default
	}

	return values
}

func (s Static) Duration(key string) time.Duration {
	value := s.Raw(key)
	parsed, err := storage.ParseSettingDuration(key, value)
	if err != nil {
		return defaultDuration(key)
	}

	return parsed
}

func (s Static) Bool(key string) bool {
	value := s.Raw(key)
	parsed, err := storage.ParseSettingBool(key, value)
	if err != nil {
		return defaultBool(key)
	}

	return parsed
}

func (s Static) Raw(key string) string {
	if value, ok := s[key]; ok {
		return value
	}

	return defaultRaw(key)
}

func defaultRaw(key string) string {
	definition, ok := storage.SettingDefinitionByKey(key)
	if !ok {
		return ""
	}

	return definition.Default
}

func defaultDuration(key string) time.Duration {
	raw := defaultRaw(key)
	parsed, err := time.ParseDuration(raw)
	if err != nil {
		return time.Second
	}

	return parsed
}

func defaultBool(key string) bool {
	raw := defaultRaw(key)
	parsed, err := strconv.ParseBool(raw)
	if err != nil {
		return false
	}

	return parsed
}
