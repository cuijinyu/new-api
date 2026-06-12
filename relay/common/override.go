package common

import (
	"fmt"
	"regexp"
	"strconv"
	"strings"

	"github.com/QuantumNous/new-api/common"
	"github.com/tidwall/gjson"
	"github.com/tidwall/sjson"
)

type ConditionOperation struct {
	Path           string      `json:"path"`             // JSON路径
	Mode           string      `json:"mode"`             // full, prefix, suffix, contains, gt, gte, lt, lte
	Value          interface{} `json:"value"`            // 匹配的值
	Invert         bool        `json:"invert"`           // 反选功能，true表示取反结果
	PassMissingKey bool        `json:"pass_missing_key"` // 未获取到json key时的行为
}

type ParamOperation struct {
	Path       string               `json:"path"`
	Mode       string               `json:"mode"` // delete, set, move, prepend, append, pass_headers
	Value      interface{}          `json:"value"`
	KeepOrigin bool                 `json:"keep_origin"`
	From       string               `json:"from,omitempty"`
	To         string               `json:"to,omitempty"`
	Conditions []ConditionOperation `json:"conditions,omitempty"` // 条件列表
	Logic      string               `json:"logic,omitempty"`      // AND, OR (默认OR)
}

func ApplyParamOverride(jsonData []byte, paramOverride map[string]interface{}, conditionContext map[string]interface{}) ([]byte, error) {
	if len(paramOverride) == 0 {
		return jsonData, nil
	}

	// 尝试断言为操作格式
	if operations, ok := tryParseOperations(paramOverride); ok {
		// 使用新方法
		return applyOperations(jsonData, operations, conditionContext)
	}

	// 直接使用旧方法
	return applyOperationsLegacy(jsonData, paramOverride, conditionContext)
}

func tryParseOperations(paramOverride map[string]interface{}) ([]ParamOperation, bool) {
	// 检查是否包含 "operations" 字段
	if opsValue, exists := paramOverride["operations"]; exists {
		if opsSlice, ok := opsValue.([]interface{}); ok {
			var operations []ParamOperation
			for _, op := range opsSlice {
				if opMap, ok := op.(map[string]interface{}); ok {
					operation := ParamOperation{}

					// 断言必要字段
					if path, ok := opMap["path"].(string); ok {
						operation.Path = path
					}
					if mode, ok := opMap["mode"].(string); ok {
						operation.Mode = mode
					} else {
						return nil, false // mode 是必需的
					}

					// 可选字段
					if value, exists := opMap["value"]; exists {
						operation.Value = value
					}
					if keepOrigin, ok := opMap["keep_origin"].(bool); ok {
						operation.KeepOrigin = keepOrigin
					}
					if from, ok := opMap["from"].(string); ok {
						operation.From = from
					}
					if to, ok := opMap["to"].(string); ok {
						operation.To = to
					}
					if logic, ok := opMap["logic"].(string); ok {
						operation.Logic = logic
					} else {
						operation.Logic = "OR" // 默认为OR
					}

					// 解析条件
					if conditions, exists := opMap["conditions"]; exists {
						if condSlice, ok := conditions.([]interface{}); ok {
							for _, cond := range condSlice {
								if condMap, ok := cond.(map[string]interface{}); ok {
									condition := ConditionOperation{}
									if path, ok := condMap["path"].(string); ok {
										condition.Path = path
									}
									if mode, ok := condMap["mode"].(string); ok {
										condition.Mode = mode
									}
									if value, ok := condMap["value"]; ok {
										condition.Value = value
									}
									if invert, ok := condMap["invert"].(bool); ok {
										condition.Invert = invert
									}
									if passMissingKey, ok := condMap["pass_missing_key"].(bool); ok {
										condition.PassMissingKey = passMissingKey
									}
									operation.Conditions = append(operation.Conditions, condition)
								}
							}
						}
					}

					operations = append(operations, operation)
				} else {
					return nil, false
				}
			}
			return operations, true
		}
	}

	return nil, false
}

func checkConditions(jsonData []byte, contextJSON string, conditions []ConditionOperation, logic string) (bool, error) {
	if len(conditions) == 0 {
		return true, nil // 没有条件，直接通过
	}
	results := make([]bool, len(conditions))
	for i, condition := range conditions {
		result, err := checkSingleCondition(jsonData, contextJSON, condition)
		if err != nil {
			return false, err
		}
		results[i] = result
	}

	if strings.ToUpper(logic) == "AND" {
		for _, result := range results {
			if !result {
				return false, nil
			}
		}
		return true, nil
	} else {
		for _, result := range results {
			if result {
				return true, nil
			}
		}
		return false, nil
	}
}

func checkSingleCondition(jsonData []byte, contextJSON string, condition ConditionOperation) (bool, error) {
	// 处理负数索引
	path := processNegativeIndex(jsonData, condition.Path)
	value := gjson.GetBytes(jsonData, path)
	if !value.Exists() && contextJSON != "" {
		value = gjson.Get(contextJSON, condition.Path)
	}
	if !value.Exists() {
		if condition.PassMissingKey {
			return true, nil
		}
		return false, nil
	}

	// 利用gjson的类型解析
	targetBytes, err := common.Marshal(condition.Value)
	if err != nil {
		return false, fmt.Errorf("failed to marshal condition value: %v", err)
	}
	targetValue := gjson.ParseBytes(targetBytes)

	result, err := compareGjsonValues(value, targetValue, strings.ToLower(condition.Mode))
	if err != nil {
		return false, fmt.Errorf("comparison failed for path %s: %v", condition.Path, err)
	}

	if condition.Invert {
		result = !result
	}
	return result, nil
}

func processNegativeIndex(jsonData []byte, path string) string {
	re := regexp.MustCompile(`\.(-\d+)`)
	matches := re.FindAllStringSubmatch(path, -1)

	if len(matches) == 0 {
		return path
	}

	result := path
	for _, match := range matches {
		negIndex := match[1]
		index, _ := strconv.Atoi(negIndex)

		arrayPath := strings.Split(path, negIndex)[0]
		if strings.HasSuffix(arrayPath, ".") {
			arrayPath = arrayPath[:len(arrayPath)-1]
		}

		array := gjson.GetBytes(jsonData, arrayPath)
		if array.IsArray() {
			length := len(array.Array())
			actualIndex := length + index
			if actualIndex >= 0 && actualIndex < length {
				result = strings.Replace(result, match[0], "."+strconv.Itoa(actualIndex), 1)
			}
		}
	}

	return result
}

// compareGjsonValues 直接比较两个gjson.Result，支持所有比较模式
func compareGjsonValues(jsonValue, targetValue gjson.Result, mode string) (bool, error) {
	switch mode {
	case "full":
		return compareEqual(jsonValue, targetValue)
	case "prefix":
		return strings.HasPrefix(jsonValue.String(), targetValue.String()), nil
	case "suffix":
		return strings.HasSuffix(jsonValue.String(), targetValue.String()), nil
	case "contains":
		return strings.Contains(jsonValue.String(), targetValue.String()), nil
	case "gt":
		return compareNumeric(jsonValue, targetValue, "gt")
	case "gte":
		return compareNumeric(jsonValue, targetValue, "gte")
	case "lt":
		return compareNumeric(jsonValue, targetValue, "lt")
	case "lte":
		return compareNumeric(jsonValue, targetValue, "lte")
	default:
		return false, fmt.Errorf("unsupported comparison mode: %s", mode)
	}
}

func compareEqual(jsonValue, targetValue gjson.Result) (bool, error) {
	// 对null值特殊处理：两个都是null返回true，一个是null另一个不是返回false
	if jsonValue.Type == gjson.Null || targetValue.Type == gjson.Null {
		return jsonValue.Type == gjson.Null && targetValue.Type == gjson.Null, nil
	}

	// 对布尔值特殊处理
	if (jsonValue.Type == gjson.True || jsonValue.Type == gjson.False) &&
		(targetValue.Type == gjson.True || targetValue.Type == gjson.False) {
		return jsonValue.Bool() == targetValue.Bool(), nil
	}

	// 如果类型不同，报错
	if jsonValue.Type != targetValue.Type {
		return false, fmt.Errorf("compare for different types, got %v and %v", jsonValue.Type, targetValue.Type)
	}

	switch jsonValue.Type {
	case gjson.True, gjson.False:
		return jsonValue.Bool() == targetValue.Bool(), nil
	case gjson.Number:
		return jsonValue.Num == targetValue.Num, nil
	case gjson.String:
		return jsonValue.String() == targetValue.String(), nil
	default:
		return jsonValue.String() == targetValue.String(), nil
	}
}

func compareNumeric(jsonValue, targetValue gjson.Result, operator string) (bool, error) {
	// 只有数字类型才支持数值比较
	if jsonValue.Type != gjson.Number || targetValue.Type != gjson.Number {
		return false, fmt.Errorf("numeric comparison requires both values to be numbers, got %v and %v", jsonValue.Type, targetValue.Type)
	}

	jsonNum := jsonValue.Num
	targetNum := targetValue.Num

	switch operator {
	case "gt":
		return jsonNum > targetNum, nil
	case "gte":
		return jsonNum >= targetNum, nil
	case "lt":
		return jsonNum < targetNum, nil
	case "lte":
		return jsonNum <= targetNum, nil
	default:
		return false, fmt.Errorf("unsupported numeric operator: %s", operator)
	}
}

// applyOperationsLegacy 原参数覆盖方法
func recordParamOverrideAudit(conditionContext map[string]interface{}, mode string, path string) {
	if conditionContext == nil {
		return
	}
	raw, ok := conditionContext["__param_override_audit"]
	if !ok {
		return
	}
	audit, ok := raw.(*[]string)
	if !ok || audit == nil {
		return
	}
	*audit = append(*audit, fmt.Sprintf("%s:%s", mode, path))
}

func applyOperationsLegacy(jsonData []byte, paramOverride map[string]interface{}, conditionContext map[string]interface{}) ([]byte, error) {
	if len(paramOverride) == 0 {
		return jsonData, nil
	}

	result := jsonData
	for key, value := range paramOverride {
		next, err := sjson.SetBytes(result, escapeSjsonLiteralKey(key), value)
		if err != nil {
			return nil, err
		}
		result = next
		recordParamOverrideAudit(conditionContext, "set", key)
	}

	return result, nil
}

func escapeSjsonLiteralKey(key string) string {
	if !strings.ContainsAny(key, ".*?\\") {
		return key
	}
	var sb strings.Builder
	sb.Grow(len(key) + 4)
	for i := 0; i < len(key); i++ {
		switch key[i] {
		case '.', '*', '?', '\\':
			sb.WriteByte('\\')
		}
		sb.WriteByte(key[i])
	}
	return sb.String()
}

func applyOperations(jsonData []byte, operations []ParamOperation, conditionContext map[string]interface{}) ([]byte, error) {
	var contextJSON string
	if conditionContext != nil && len(conditionContext) > 0 {
		ctxBytes, err := common.Marshal(conditionContext)
		if err != nil {
			return nil, fmt.Errorf("failed to marshal condition context: %v", err)
		}
		contextJSON = string(ctxBytes)
	}

	result := jsonData
	for _, op := range operations {
		// 检查条件是否满足
		ok, err := checkConditions(result, contextJSON, op.Conditions, op.Logic)
		if err != nil {
			return nil, err
		}
		if !ok {
			continue // 条件不满足，跳过当前操作
		}
		// 处理路径中的负数索引
		opPath := processNegativeIndex(result, op.Path)
		opFrom := processNegativeIndex(result, op.From)
		opTo := processNegativeIndex(result, op.To)

		switch op.Mode {
		case "delete":
			result, err = sjson.DeleteBytes(result, opPath)
			recordParamOverrideAudit(conditionContext, op.Mode, opPath)
		case "set":
			if op.KeepOrigin && gjson.GetBytes(result, opPath).Exists() {
				continue
			}
			result, err = sjson.SetBytes(result, opPath, op.Value)
			recordParamOverrideAudit(conditionContext, op.Mode, opPath)
		case "move":
			result, err = moveValue(result, opFrom, opTo)
			recordParamOverrideAudit(conditionContext, op.Mode, opFrom+"->"+opTo)
		case "prepend":
			result, err = modifyValue(result, opPath, op.Value, op.KeepOrigin, true)
			recordParamOverrideAudit(conditionContext, op.Mode, opPath)
		case "append":
			result, err = modifyValue(result, opPath, op.Value, op.KeepOrigin, false)
			recordParamOverrideAudit(conditionContext, op.Mode, opPath)
		case "pass_headers":
			continue
		default:
			return nil, fmt.Errorf("unknown operation: %s", op.Mode)
		}
		if err != nil {
			return nil, fmt.Errorf("operation %s failed: %v", op.Mode, err)
		}
	}
	return result, nil
}

func moveValue(jsonData []byte, fromPath, toPath string) ([]byte, error) {
	sourceValue := gjson.GetBytes(jsonData, fromPath)
	if !sourceValue.Exists() {
		return jsonData, fmt.Errorf("source path does not exist: %s", fromPath)
	}
	result, err := sjson.SetBytes(jsonData, toPath, sourceValue.Value())
	if err != nil {
		return nil, err
	}
	return sjson.DeleteBytes(result, fromPath)
}

func modifyValue(jsonData []byte, path string, value interface{}, keepOrigin, isPrepend bool) ([]byte, error) {
	current := gjson.GetBytes(jsonData, path)
	switch {
	case current.IsArray():
		return modifyArray(jsonData, path, value, isPrepend)
	case current.Type == gjson.String:
		return modifyString(jsonData, path, value, isPrepend)
	case current.Type == gjson.JSON:
		return mergeObjects(jsonData, path, value, keepOrigin)
	}
	return jsonData, fmt.Errorf("operation not supported for type: %v", current.Type)
}

func modifyArray(jsonData []byte, path string, value interface{}, isPrepend bool) ([]byte, error) {
	current := gjson.GetBytes(jsonData, path)
	var newArray []interface{}
	// 添加新值
	addValue := func() {
		if arr, ok := value.([]interface{}); ok {
			newArray = append(newArray, arr...)
		} else {
			newArray = append(newArray, value)
		}
	}
	// 添加原值
	addOriginal := func() {
		current.ForEach(func(_, val gjson.Result) bool {
			newArray = append(newArray, val.Value())
			return true
		})
	}
	if isPrepend {
		addValue()
		addOriginal()
	} else {
		addOriginal()
		addValue()
	}
	return sjson.SetBytes(jsonData, path, newArray)
}

func modifyString(jsonData []byte, path string, value interface{}, isPrepend bool) ([]byte, error) {
	current := gjson.GetBytes(jsonData, path)
	valueStr := fmt.Sprintf("%v", value)
	var newStr string
	if isPrepend {
		newStr = valueStr + current.String()
	} else {
		newStr = current.String() + valueStr
	}
	return sjson.SetBytes(jsonData, path, newStr)
}

func mergeObjects(jsonData []byte, path string, value interface{}, keepOrigin bool) ([]byte, error) {
	current := gjson.GetBytes(jsonData, path)
	var currentMap, newMap map[string]interface{}

	// 解析当前值
	if err := common.UnmarshalJsonStr(current.Raw, &currentMap); err != nil {
		return nil, err
	}
	// 解析新值
	switch v := value.(type) {
	case map[string]interface{}:
		newMap = v
	default:
		jsonBytes, _ := common.Marshal(v)
		if err := common.Unmarshal(jsonBytes, &newMap); err != nil {
			return nil, err
		}
	}
	// 合并
	result := make(map[string]interface{})
	for k, v := range currentMap {
		result[k] = v
	}
	for k, v := range newMap {
		if !keepOrigin || result[k] == nil {
			result[k] = v
		}
	}
	return sjson.SetBytes(jsonData, path, result)
}

// ExtractPassHeaders extracts header names from pass_headers operations in paramOverride.
func ExtractPassHeaders(paramOverride map[string]interface{}) []string {
	operations, ok := tryParseOperations(paramOverride)
	if !ok {
		return nil
	}
	var headers []string
	for _, op := range operations {
		if op.Mode != "pass_headers" {
			continue
		}
		switch v := op.Value.(type) {
		case []interface{}:
			for _, item := range v {
				if s, ok := item.(string); ok {
					headers = append(headers, s)
				}
			}
		case string:
			headers = append(headers, v)
		}
	}
	return headers
}

// BuildParamOverrideContext 提供 ApplyParamOverride 可用的上下文信息。
// 目前内置以下字段：
//   - model：优先使用上游模型名（UpstreamModelName），若不存在则回落到原始模型名（OriginModelName）。
//   - upstream_model：始终为通道映射后的上游模型名。
//   - original_model：请求最初指定的模型名。
func BuildParamOverrideContext(info *RelayInfo) map[string]interface{} {
	if info == nil || info.ChannelMeta == nil {
		return nil
	}

	ctx := make(map[string]interface{})
	if info.UpstreamModelName != "" {
		ctx["model"] = info.UpstreamModelName
		ctx["upstream_model"] = info.UpstreamModelName
	}
	if info.OriginModelName != "" {
		ctx["original_model"] = info.OriginModelName
		if _, exists := ctx["model"]; !exists {
			ctx["model"] = info.OriginModelName
		}
	}

	if len(ctx) == 0 {
		ctx["__param_override_audit"] = &info.ParamOverrideAudit
		return ctx
	}
	ctx["__param_override_audit"] = &info.ParamOverrideAudit
	return ctx
}
