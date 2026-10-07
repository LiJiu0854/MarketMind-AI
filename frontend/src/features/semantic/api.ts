import { apiJson } from '../../lib/api'
import type { Page } from '../../lib/types'
import type { SemanticReview, SemanticReviewCreated } from './types'

export const listSemanticReviews = (productId: number) => apiJson<Page<SemanticReview>>(`/products/${productId}/semantic-reviews`)
export const startSemanticReview = (productId: number) => apiJson<SemanticReviewCreated>(`/products/${productId}/semantic-reviews`, { method: 'POST' })
export const getSemanticReview = (productId: number, reviewId: number) => apiJson<SemanticReview>(`/products/${productId}/semantic-reviews/${reviewId}`)
