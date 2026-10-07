<script setup lang="ts">
import { watch } from 'vue'
import { useRouter } from 'vue-router'
import { currentUser } from './lib/session'

const router = useRouter()
watch(currentUser, (user) => { if (!user && router.currentRoute.value.path !== '/login') void router.replace('/login') })
</script>
<template><RouterView /></template>
