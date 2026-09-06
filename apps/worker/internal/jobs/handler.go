package jobs

import (
	"context"
	"fmt"
	"sort"

	"github.com/elei-io/pithosys/packages/storage"
)

type Handler interface {
	Type() storage.JobType
	Handle(context.Context, storage.JobRun) (storage.JobRunPayload, error)
}

type Registry struct {
	handlers map[storage.JobType]Handler
}

func NewRegistry(handlers ...Handler) (*Registry, error) {
	registry := &Registry{
		handlers: map[storage.JobType]Handler{},
	}

	for _, handler := range handlers {
		if err := registry.Register(handler); err != nil {
			return nil, err
		}
	}

	return registry, nil
}

func (r *Registry) Register(handler Handler) error {
	if handler == nil {
		return fmt.Errorf("register job handler: nil handler")
	}
	jobType := handler.Type()
	if jobType == "" {
		return fmt.Errorf("register job handler: empty job type")
	}
	if _, exists := r.handlers[jobType]; exists {
		return fmt.Errorf("register job handler: duplicate handler for %q", jobType)
	}

	r.handlers[jobType] = handler
	return nil
}

func (r *Registry) Get(jobType storage.JobType) (Handler, bool) {
	if r == nil {
		return nil, false
	}

	handler, ok := r.handlers[jobType]
	return handler, ok
}

func (r *Registry) Types() []storage.JobType {
	if r == nil {
		return nil
	}

	types := make([]storage.JobType, 0, len(r.handlers))
	for jobType := range r.handlers {
		types = append(types, jobType)
	}
	sort.Slice(types, func(i, j int) bool {
		return types[i] < types[j]
	})

	return types
}
