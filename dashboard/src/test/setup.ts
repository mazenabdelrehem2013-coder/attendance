import '@testing-library/jest-dom/vitest'

import { cleanup, configure } from '@testing-library/react'
import { afterEach } from 'vitest'

// "findBy..." waits up to 1 s by default. When several test files run at once on a busy PC,
// a page can take longer to appear; that made tests fail now and then. Wait up to 5 s instead
// (a passing test is not slower: it continues as soon as the text is there).
configure({ asyncUtilTimeout: 5000 })

// Remove everything rendered by a test before the next one starts.
afterEach(cleanup)
