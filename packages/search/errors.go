package search

import (
	"errors"
	"fmt"
)

var ErrValidation = errors.New("relicql validation error")

func ValidationError(err error) error {
	if err == nil {
		return nil
	}
	return fmt.Errorf("%w: %w", ErrValidation, err)
}

func IsValidationError(err error) bool {
	return errors.Is(err, ErrValidation)
}
