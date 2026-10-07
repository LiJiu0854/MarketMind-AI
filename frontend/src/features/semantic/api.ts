import { apiJson } from '../../lib/api'
import type { Page } from '../../lib/types'
import type { SemanticReview, SemanticReviewCreated } from './types'

export const listSemanticReviews = (productId: number, page = 1) => apiJson<Page<SemanticReview>>(`/products/${productId}/semantic-reviews?page=${page}`)
export const startSemanticReview = (productId: number) => apiJson<SemanticReviewCreated>(`/products/${productId}/semantic-reviews`, { method: 'POST' })
export const getSemanticReview = (productId: number, reviewId: number) => apiJson<SemanticReview>(`/products/${productId}/semantic-reviews/${reviewId}`)
