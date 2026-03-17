package common

import "strings"

var (
	// OpenAIResponseOnlyModels is a list of models that are only available for OpenAI responses.
	// Use "prefix:" for prefix matching, otherwise exact match.
	OpenAIResponseOnlyModels = []string{
		// pro models (Responses API only)
		"prefix:o1-pro",
		"prefix:o3-pro",
		"prefix:gpt-5-pro",
		"prefix:gpt-5.2-pro",
		"prefix:gpt-5.4-pro",
		// deep-research models
		"prefix:o3-deep-research",
		"prefix:o4-mini-deep-research",
		// codex models
		"codex-mini-latest",
		"prefix:gpt-5-codex",
		"prefix:gpt-5.1-codex",
		"prefix:gpt-5.2-codex",
		"prefix:gpt-5.3-codex",
	}
	ImageGenerationModels = []string{
		"dall-e-3",
		"dall-e-2",
		"gpt-image-1",
		"prefix:imagen-",
		"flux-",
		"flux.1-",
	}
)

func IsOpenAIResponseOnlyModel(modelName string) bool {
	for _, m := range OpenAIResponseOnlyModels {
		if strings.HasPrefix(m, "prefix:") {
			if strings.HasPrefix(modelName, strings.TrimPrefix(m, "prefix:")) {
				return true
			}
		} else if modelName == m {
			return true
		}
	}
	return false
}

func IsImageGenerationModel(modelName string) bool {
	modelName = strings.ToLower(modelName)
	for _, m := range ImageGenerationModels {
		if strings.Contains(modelName, m) {
			return true
		}
		if strings.HasPrefix(m, "prefix:") && strings.HasPrefix(modelName, strings.TrimPrefix(m, "prefix:")) {
			return true
		}
	}
	return false
}
