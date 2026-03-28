package logger

import (
	"runtime"
	"sync"
	"time"
)

var (
	runtimeCollectorOnce sync.Once
	runtimeStopCh        chan struct{}
	runtimeWg            sync.WaitGroup

	activeConnectionsFn func() int64
)

func SetActiveConnectionsProvider(fn func() int64) {
	activeConnectionsFn = fn
}

func StartRuntimeCollector() {
	if !metricsEnabled {
		return
	}
	runtimeCollectorOnce.Do(func() {
		runtimeStopCh = make(chan struct{})
		runtimeWg.Add(1)
		go runRuntimeCollector()
	})
}

func StopRuntimeCollector() {
	if runtimeStopCh == nil {
		return
	}
	select {
	case <-runtimeStopCh:
	default:
		close(runtimeStopCh)
	}
	runtimeWg.Wait()
}

func runRuntimeCollector() {
	defer runtimeWg.Done()
	ticker := time.NewTicker(60 * time.Second)
	defer ticker.Stop()

	collect()
	for {
		select {
		case <-ticker.C:
			collect()
		case <-runtimeStopCh:
			return
		}
	}
}

func collect() {
	var m runtime.MemStats
	runtime.ReadMemStats(&m)

	heapMB := float64(m.HeapAlloc) / (1024 * 1024)
	goroutines := runtime.NumGoroutine()

	var gcPauseMs float64
	if m.NumGC > 0 {
		idx := (m.NumGC + 255) % 256
		gcPauseMs = float64(m.PauseNs[idx]) / 1e6
	}

	var activeConns int64
	if activeConnectionsFn != nil {
		activeConns = activeConnectionsFn()
	}

	emf := NewEMF()
	if emf == nil {
		return
	}
	emf.AddMetricSet(RuntimeDims, RuntimeMetrics).
		Metric("ActiveConnections", activeConns).
		Metric("GoroutineCount", goroutines).
		Metric("HeapAllocMB", heapMB).
		Metric("GCPauseMs", gcPauseMs).
		Emit()
}
