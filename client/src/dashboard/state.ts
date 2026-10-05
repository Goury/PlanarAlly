import { reactive } from "vue";

export const dashboardState = reactive({
    adminEnabled: false,
    canCreateCampaigns: true,
    chunksProcessed: new Set<number>(),
    chunkLength: 0,
});
