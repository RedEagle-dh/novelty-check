Chat models trained to be safe refuse harmful requests. My idea: automatically find a short
string of tokens that, appended to any harmful request, makes the model begin its answer with an
affirmative phrase and then comply. The string is optimised with gradients with respect to the
one-hot token choices, which propose promising single-token swaps; candidates are evaluated and
the best one is kept. Optimising over many requests and several open-weight models at once should
make the same string work on closed commercial chat models too.
