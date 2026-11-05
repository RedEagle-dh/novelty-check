Servers that run large language models waste a lot of GPU memory: for every request they reserve
one contiguous buffer for the stored attention state of earlier tokens, sized for the longest
possible output. My idea: split that state into small fixed-size chunks that can sit anywhere in
GPU memory, keep a per-request table that maps logical positions to chunks (the way an operating
system maps a process's pages), and let requests share chunks, for example a common prompt
prefix, copying a chunk only when one request writes to it. The server could then batch far more
requests at once and reach much higher throughput.
