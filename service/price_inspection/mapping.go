package price_inspection

import (
	"errors"
	"math"
	"sort"
	"strings"
	"unicode"

	"github.com/QuantumNous/new-api/model"

	"gorm.io/gorm"
)

type MappingRequest struct {
	ChannelID        int    `json:"channel_id"`
	ChannelType      int    `json:"channel_type"`
	LocalModelName   string `json:"local_model_name"`
	SourceProvider   string `json:"source_provider"`
	SourceModelID    string `json:"source_model_id"`
	CanonicalModelID string `json:"canonical_model_id"`
	Scenario         string `json:"scenario"`
	Priority         int    `json:"priority"`
	Enabled          *bool  `json:"enabled"`
	Confidence       string `json:"confidence"`
	Note             string `json:"note"`
}

type SuggestMappingsRequest struct {
	SourceProvider string  `json:"source_provider"`
	GeneratedAt    int64   `json:"generated_at"`
	ChannelType    int     `json:"channel_type"`
	ModelName      string  `json:"model_name"`
	Limit          int     `json:"limit"`
	MinScore       float64 `json:"min_score"`
	OnlyMissing    *bool   `json:"only_missing"`
}

type MappingSuggestion struct {
	CoverageReportID       int64   `json:"coverage_report_id"`
	GeneratedAt            int64   `json:"generated_at"`
	ChannelType            int     `json:"channel_type"`
	ChannelTypeName        string  `json:"channel_type_name"`
	LocalModelName         string  `json:"local_model_name"`
	Scenario               string  `json:"scenario"`
	SampleLogCount         int64   `json:"sample_log_count"`
	SuggestedSourceModelID string  `json:"suggested_source_model_id"`
	SuggestedLocalName     string  `json:"suggested_local_name"`
	Score                  float64 `json:"score"`
	Confidence             string  `json:"confidence"`
	Reason                 string  `json:"reason"`
}

type snapshotCandidate struct {
	ModelID        string
	LocalModelName string
	Normalized     string
	Tokens         []string
}

func CreateMapping(req MappingRequest) (*model.PriceModelMapping, error) {
	mapping, err := mappingFromRequest(req, nil)
	if err != nil {
		return nil, err
	}
	if err := model.CreatePriceModelMapping(mapping); err != nil {
		return nil, err
	}
	return mapping, nil
}

func UpdateMapping(id int64, req MappingRequest) (*model.PriceModelMapping, error) {
	existing, err := model.GetPriceModelMappingByID(id)
	if err != nil {
		return nil, err
	}
	mapping, err := mappingFromRequest(req, existing)
	if err != nil {
		return nil, err
	}
	mapping.ID = id
	if err := model.UpdatePriceModelMapping(mapping); err != nil {
		return nil, err
	}
	return mapping, nil
}

func SuggestMappings(req SuggestMappingsRequest) ([]MappingSuggestion, error) {
	req.SourceProvider = normalizeProvider(req.SourceProvider)
	if req.SourceProvider == "" {
		req.SourceProvider = ProviderOpenRouter
	}
	if req.Limit <= 0 {
		req.Limit = 50
	}
	if req.Limit > 200 {
		req.Limit = 200
	}
	if req.MinScore <= 0 {
		req.MinScore = 0.58
	}
	onlyMissing := true
	if req.OnlyMissing != nil {
		onlyMissing = *req.OnlyMissing
	}
	if req.GeneratedAt == 0 {
		generatedAt, err := model.GetLatestPriceInspectionCoverageGeneratedAt(req.SourceProvider)
		if err != nil {
			return nil, err
		}
		req.GeneratedAt = generatedAt
	}
	if req.GeneratedAt == 0 {
		return []MappingSuggestion{}, nil
	}

	coverageRows, err := loadCoverageRowsForSuggestion(req, onlyMissing)
	if err != nil {
		return nil, err
	}
	candidates, err := loadSnapshotCandidates(req.SourceProvider)
	if err != nil {
		return nil, err
	}

	suggestions := make([]MappingSuggestion, 0, len(coverageRows))
	for _, row := range coverageRows {
		best, score, reason := bestSnapshotCandidate(row.ModelName, candidates)
		if best.ModelID == "" || score < req.MinScore {
			continue
		}
		suggestions = append(suggestions, MappingSuggestion{
			CoverageReportID:       row.ID,
			GeneratedAt:            row.GeneratedAt,
			ChannelType:            row.ChannelType,
			ChannelTypeName:        row.ChannelTypeName,
			LocalModelName:         row.ModelName,
			Scenario:               row.Scenario,
			SampleLogCount:         row.SampleLogCount,
			SuggestedSourceModelID: best.ModelID,
			SuggestedLocalName:     best.LocalModelName,
			Score:                  math.Round(score*10000) / 10000,
			Confidence:             confidenceForScore(score),
			Reason:                 reason,
		})
	}
	sort.Slice(suggestions, func(i, j int) bool {
		if suggestions[i].Score == suggestions[j].Score {
			return suggestions[i].SampleLogCount > suggestions[j].SampleLogCount
		}
		return suggestions[i].Score > suggestions[j].Score
	})
	if len(suggestions) > req.Limit {
		suggestions = suggestions[:req.Limit]
	}
	return suggestions, nil
}

func mappingFromRequest(req MappingRequest, existing *model.PriceModelMapping) (*model.PriceModelMapping, error) {
	mapping := &model.PriceModelMapping{}
	if existing != nil {
		*mapping = *existing
	}
	if strings.TrimSpace(req.LocalModelName) != "" {
		mapping.LocalModelName = strings.TrimSpace(req.LocalModelName)
	}
	if strings.TrimSpace(req.SourceProvider) != "" {
		mapping.SourceProvider = normalizeProvider(req.SourceProvider)
	}
	if strings.TrimSpace(mapping.SourceProvider) == "" {
		mapping.SourceProvider = ProviderOpenRouter
	}
	if strings.TrimSpace(req.SourceModelID) != "" {
		mapping.SourceModelID = strings.TrimSpace(req.SourceModelID)
	}
	if strings.TrimSpace(req.CanonicalModelID) != "" {
		mapping.CanonicalModelID = strings.TrimSpace(req.CanonicalModelID)
	}
	if mapping.CanonicalModelID == "" {
		mapping.CanonicalModelID = mapping.SourceModelID
	}
	if strings.TrimSpace(req.Scenario) != "" {
		mapping.Scenario = strings.TrimSpace(req.Scenario)
	}
	if mapping.Scenario == "" && mapping.LocalModelName != "" {
		mapping.Scenario = detectScenario(req.ChannelType, mapping.LocalModelName)
	}
	if req.ChannelID != 0 || existing == nil {
		mapping.ChannelID = req.ChannelID
	}
	if req.ChannelType != 0 || existing == nil {
		mapping.ChannelType = req.ChannelType
	}
	if req.Priority != 0 || existing == nil {
		mapping.Priority = req.Priority
	}
	if req.Enabled != nil {
		mapping.Enabled = *req.Enabled
	} else if existing == nil {
		mapping.Enabled = true
	}
	if strings.TrimSpace(req.Confidence) != "" {
		mapping.Confidence = strings.TrimSpace(req.Confidence)
	}
	if mapping.Confidence == "" {
		mapping.Confidence = "manual"
	}
	if strings.TrimSpace(req.Note) != "" {
		mapping.Note = strings.TrimSpace(req.Note)
	}

	if mapping.LocalModelName == "" {
		return nil, errors.New("local_model_name is required")
	}
	if mapping.SourceProvider == "" {
		return nil, errors.New("source_provider is required")
	}
	if mapping.SourceModelID == "" {
		return nil, errors.New("source_model_id is required")
	}
	return mapping, nil
}

func loadCoverageRowsForSuggestion(req SuggestMappingsRequest, onlyMissing bool) ([]model.PriceInspectionCoverageReport, error) {
	tx := model.DB.Model(&model.PriceInspectionCoverageReport{}).
		Where("source_provider = ? AND generated_at = ?", req.SourceProvider, req.GeneratedAt)
	if onlyMissing {
		tx = tx.Where("reason_code = ?", "missing_model_mapping")
	}
	if req.ChannelType > 0 {
		tx = tx.Where("channel_type = ?", req.ChannelType)
	}
	if strings.TrimSpace(req.ModelName) != "" {
		tx = tx.Where("model_name = ?", strings.TrimSpace(req.ModelName))
	}
	var rows []model.PriceInspectionCoverageReport
	err := tx.Order("sample_log_count DESC, channel_count DESC, id DESC").Limit(req.Limit * 3).Find(&rows).Error
	return rows, err
}

func loadSnapshotCandidates(sourceProvider string) ([]snapshotCandidate, error) {
	sourceProvider = normalizeProvider(sourceProvider)
	if sourceProvider == "" {
		sourceProvider = ProviderOpenRouter
	}
	var snapshots []model.PriceSourceSnapshot
	if err := model.DB.Where("source_provider = ?", sourceProvider).Order("fetched_at DESC, id DESC").Find(&snapshots).Error; err != nil {
		return nil, err
	}
	if len(snapshots) > 0 {
		return priceSourceSnapshotCandidates(snapshots), nil
	}
	if sourceProvider == ProviderOpenRouter {
		return loadOpenRouterSnapshotCandidates()
	}
	return []snapshotCandidate{}, nil
}

func loadOpenRouterSnapshotCandidates() ([]snapshotCandidate, error) {
	var snapshots []model.OpenRouterPriceSnapshot
	if err := model.DB.Order("fetched_at DESC, id DESC").Find(&snapshots).Error; err != nil {
		return nil, err
	}
	priceSnapshots := make([]model.PriceSourceSnapshot, 0, len(snapshots))
	for _, snapshot := range snapshots {
		priceSnapshots = append(priceSnapshots, priceSourceSnapshotFromOpenRouter(snapshot))
	}
	return priceSourceSnapshotCandidates(priceSnapshots), nil
}

func priceSourceSnapshotCandidates(snapshots []model.PriceSourceSnapshot) []snapshotCandidate {
	seen := map[string]bool{}
	candidates := make([]snapshotCandidate, 0, len(snapshots))
	for _, snapshot := range snapshots {
		if snapshot.ModelID == "" || seen[snapshot.ModelID] {
			continue
		}
		seen[snapshot.ModelID] = true
		name := snapshot.LocalModelName
		if name == "" {
			name = snapshot.ModelID
		}
		tokenSource := snapshot.ModelID + " " + name
		candidates = append(candidates, snapshotCandidate{
			ModelID:        snapshot.ModelID,
			LocalModelName: name,
			Normalized:     normalizeModelName(tokenSource),
			Tokens:         tokenizeModelName(tokenSource),
		})
	}
	return candidates
}

func bestSnapshotCandidate(localModel string, candidates []snapshotCandidate) (snapshotCandidate, float64, string) {
	localNormalized := normalizeModelName(localModel)
	localTokens := tokenizeModelName(localModel)
	var best snapshotCandidate
	bestScore := 0.0
	bestReason := ""
	for _, candidate := range candidates {
		score, reason := modelSimilarity(localNormalized, localTokens, candidate)
		if score > bestScore {
			best = candidate
			bestScore = score
			bestReason = reason
		}
	}
	return best, bestScore, bestReason
}

func modelSimilarity(localNormalized string, localTokens []string, candidate snapshotCandidate) (float64, string) {
	if localNormalized == "" || candidate.Normalized == "" {
		return 0, "empty_name"
	}
	if localNormalized == candidate.Normalized || normalizeModelName(candidate.LocalModelName) == localNormalized {
		return 1, "normalized_exact_match"
	}
	score := tokenDiceScore(localTokens, candidate.Tokens)
	reason := "token_overlap"
	if strings.Contains(candidate.Normalized, localNormalized) || strings.Contains(localNormalized, normalizeModelName(candidate.LocalModelName)) {
		score += 0.18
		reason = "normalized_contains"
	}
	if sameModelFamily(localTokens, candidate.Tokens) {
		score += 0.08
	}
	if shareVersionTokens(localTokens, candidate.Tokens) {
		score += 0.08
	}
	if score > 1 {
		score = 1
	}
	return score, reason
}

func tokenDiceScore(left, right []string) float64 {
	if len(left) == 0 || len(right) == 0 {
		return 0
	}
	rightCounts := map[string]int{}
	for _, token := range right {
		rightCounts[token]++
	}
	commonCount := 0
	for _, token := range left {
		if rightCounts[token] > 0 {
			commonCount++
			rightCounts[token]--
		}
	}
	return float64(2*commonCount) / float64(len(left)+len(right))
}

func sameModelFamily(left, right []string) bool {
	families := []string{"claude", "sonnet", "opus", "haiku", "gemini", "gpt", "deepseek", "glm", "kimi", "minimax"}
	leftSet := tokenSet(left)
	rightSet := tokenSet(right)
	for _, family := range families {
		if leftSet[family] && rightSet[family] {
			return true
		}
	}
	return false
}

func shareVersionTokens(left, right []string) bool {
	leftSet := tokenSet(left)
	for _, token := range right {
		if leftSet[token] && isNumericToken(token) {
			return true
		}
	}
	return false
}

func tokenSet(tokens []string) map[string]bool {
	out := map[string]bool{}
	for _, token := range tokens {
		out[token] = true
	}
	return out
}

func isNumericToken(token string) bool {
	if token == "" {
		return false
	}
	for _, r := range token {
		if !unicode.IsDigit(r) {
			return false
		}
	}
	return true
}

func tokenizeModelName(value string) []string {
	value = strings.ToLower(value)
	var tokens []string
	var current []rune
	var currentKind int
	flush := func() {
		if len(current) == 0 {
			return
		}
		token := string(current)
		if token != "" {
			tokens = append(tokens, token)
		}
		current = nil
		currentKind = 0
	}
	for _, r := range value {
		kind := 0
		if unicode.IsLetter(r) {
			kind = 1
		} else if unicode.IsDigit(r) {
			kind = 2
		}
		if kind == 0 {
			flush()
			continue
		}
		if currentKind != 0 && currentKind != kind {
			flush()
		}
		currentKind = kind
		current = append(current, r)
	}
	flush()
	return tokens
}

func confidenceForScore(score float64) string {
	if score >= 0.9 {
		return "high"
	}
	if score >= 0.72 {
		return "medium"
	}
	return "low"
}

func IsRecordNotFound(err error) bool {
	return errors.Is(err, gorm.ErrRecordNotFound)
}
