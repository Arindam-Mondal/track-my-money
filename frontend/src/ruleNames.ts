import { createContext } from 'react'

/** Rule id -> name, so a category set by a rule can say which one. Provided by App. */
export const RuleNames = createContext<ReadonlyMap<number, string>>(new Map())
